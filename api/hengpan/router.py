"""
横盘选股接口：发起扫描、查询进度、停止扫描、历史快照。
任务状态复用 api/task_manager.py；扫描日和统计在任务对象里没有对应字段，存在本模块的 _extras 里。
"""
import traceback
from datetime import datetime
from typing import Dict, List, Literal, Optional

import pandas as pd
from colorama import Fore, Style
from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..data_fetcher import BaostockConnectionManager, fetch_industry_data, fetch_stock_basics
from ..platform_scanner import select_markets
from ..store import db as store_db
from ..store.reader import latest_date as local_latest_date
from ..task_manager import TaskStatus, task_manager
from .anchored_box import (AMP_MULTIPLE, BOX_HEIGHT, BOX_TYPE, DOJI_AMPLITUDE, LOOKBACK,
                           MAX_AMPLITUDE, MAX_BREACH)
from .tolerant_box import MAX_CONSECUTIVE_BREACH
from .fetcher import resolve_scan_date
from .history import cleanup_histories, delete_history, get_history, list_histories, save_history
from .scanner import new_stats, scan_anchored_box, select_stocks

router = APIRouter()

# task_id -> {"params", "scan_date", "stats"}；只记录本页面发起的任务
_extras: Dict[str, Dict] = {}


class HengpanRule(BaseModel):
    """一组箱体规则，默认值即方案文档第 10 节的参数表。"""
    box_type: Literal["fixed", "amplitude", "tolerant"] = Field(
        BOX_TYPE,
        description="箱体模式：fixed 固定箱高（十字星中点为上轨、普通 K 线中点为中轨）/ "
                    "amplitude 振幅倍数（末端 K 线最高价往上、最低价往下各延伸若干倍振幅）/ "
                    "tolerant 容刺箱体（用实体中心价寻找主体区间）")
    doji_amplitude: float = Field(DOJI_AMPLITUDE, gt=0, le=0.05,
                                  description="十字星振幅上限：末端 K 线振幅不超过它算十字星，0.005 即 0.5%；只对 fixed 生效")
    box_height: float = Field(BOX_HEIGHT, gt=0, le=0.3, description="箱体固定高度，0.04 即 4%；只对 fixed 生效")
    amp_multiple: float = Field(AMP_MULTIPLE, gt=0, le=20,
                                description="振幅倍数：上下各延伸几倍末端振幅，1 即上下各一倍；只对 amplitude 生效")
    max_amplitude: Optional[float] = Field(
        MAX_AMPLITUDE, gt=0, le=1,
        description="末端振幅上限，0.05 即 5%：末端 K 线振幅超过它直接淘汰；留空不限。只对 amplitude 生效")
    lookback: int = Field(LOOKBACK, ge=10, le=250, description="回验的 K 线根数，不含末端这一根")
    max_breach: int = Field(MAX_BREACH, ge=0, le=20, description="回验区间允许越界的最多根数")
    max_consecutive_breach: int = Field(
        MAX_CONSECUTIVE_BREACH, ge=1, le=20,
        description="允许连续实体刺破的最多根数；只对 tolerant 生效，默认 1，即连续 2 根失败")


def _rule_key(rule: Dict) -> tuple:
    """判重只看当前模式实际使用的参数。"""
    if rule["box_type"] == "amplitude":
        used = ("amp_multiple", "max_amplitude")
    elif rule["box_type"] == "tolerant":
        used = ("box_height", "max_consecutive_breach")
    else:
        used = ("doji_amplitude", "box_height")
    return (rule["box_type"], rule["lookback"], rule["max_breach"]) + tuple(rule[name] for name in used)


def validate_rules(rules: List[Dict]) -> List[Dict]:
    """
    校验规则组并按填写顺序编号，返回 [{"id", "params"}]。

    横盘-A 和横盘-U 共用，两个页面的判重与越界校验口径因此始终一致。
    """
    seen = set()
    for index, rule in enumerate(rules, start=1):
        if rule["max_breach"] >= rule["lookback"]:
            raise HTTPException(status_code=422, detail=f"第 {index} 组规则：允许越界根数应小于回验根数")
        if rule["box_type"] == "tolerant" and rule["max_consecutive_breach"] >= rule["lookback"]:
            raise HTTPException(status_code=422, detail=f"第 {index} 组规则：连续刺破上限应小于回验根数")
        key = _rule_key(rule)
        if key in seen:
            raise HTTPException(status_code=422, detail=f"第 {index} 组规则与前面某一组完全相同，请删掉重复的一组")
        seen.add(key)
    return [{"id": str(index), "params": rule} for index, rule in enumerate(rules, start=1)]


class HengpanRuleInfo(BaseModel):
    """扫描实际使用的规则，id 用于在结果和统计里索引这一组。"""
    id: str = Field(description="规则编号，从 1 开始")
    params: HengpanRule = Field(description="这组规则的参数")


class HengpanScanRequest(BaseModel):
    """横盘选股扫描参数。多组规则共用一次取数，耗时和请求次数与只扫一组相同。"""
    rules: List[HengpanRule] = Field(default_factory=lambda: [HengpanRule()], min_length=1, max_length=6,
                                     description="箱体规则，可同时给 1~6 组，结果按组分别标注")
    scan_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$",
                                     description="扫描日 YYYY-MM-DD，须为所选周期有数据的交易日；"
                                                 "60 分钟留空取本地行情最新日期，日线留空联网探测")
    frequency: str = Field("60", pattern=r"^(d|60)$", description="K线周期：60 分钟或日线")
    markets: List[str] = Field(
        default_factory=list,
        description="只扫描指定板块：sh_main 沪市主板 / sz_main 深市主板 / sz_gem 创业板 / sh_star 科创板；留空为全部 A 股")
    max_workers: int = Field(5, ge=1, le=10, description="并发拉取数据的进程数")
    retry_attempts: int = Field(2, ge=1, le=5, description="单只股票取数失败时的重试次数")


class HengpanHistoryCleanupRequest(BaseModel):
    """历史快照清理策略；按数量和按天数二选一。"""
    keep_count: Optional[int] = Field(None, ge=1, le=1000, description="保留最新的快照数量")
    keep_days: Optional[int] = Field(None, ge=1, le=3650, description="保留最近多少天的快照")


class HengpanKline(BaseModel):
    date: str = Field(description="交易日期；60 分钟模式包含 HH:MM:SS")
    open: Optional[float] = Field(None, description="开盘价（前复权）")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    close: Optional[float] = Field(None, description="收盘价")
    volume: Optional[float] = Field(None, description="成交量（股）")
    amount: Optional[float] = Field(None, description="成交额（元）")
    turn: Optional[float] = Field(None, description="换手率（%）")


class HengpanMatch(BaseModel):
    """一只股票在某一组规则下的判定结果。上轨下轨按规则各不相同，所以逐组给出。"""
    mode: str = Field(description="命中模式：doji 十字星 / normal 普通 K 线 / amplitude 振幅模式 / "
                                  "tolerant 容刺箱体")
    amplitude: float = Field(description="末端振幅 (high - low) / close")
    upper: float = Field(description="箱体上轨（前复权价格）")
    lower: float = Field(description="箱体下轨（前复权价格）")
    actual_range: Optional[float] = Field(
        None,
        description="该规则回验区间加末端 K 线的实际震荡幅度：(最高价 - 最低价) / 最低价"
    )
    over_amplitude: bool = Field(False, description="末端振幅超过这组规则的振幅上限，直接淘汰；只在振幅模式下可能为真")
    breach_full: int = Field(description="整体口径越界根数：最高价高于上轨或最低价低于下轨")
    breach_body: int = Field(description="实体口径越界根数：只看开盘价和收盘价")
    longest_consecutive_breach: Optional[int] = Field(
        None, description="最长连续实体刺破根数；只对 tolerant 模式返回")
    passed_full: bool = Field(description="整体口径下是否入选（默认口径）")
    passed_body: bool = Field(description="实体口径下是否入选")
    avg_amount: Optional[float] = Field(None, description="回验区间平均成交额（元）")
    avg_turn: Optional[float] = Field(None, description="回验区间平均换手率（%）")
    lookback_start: Optional[str] = Field(None, description="回验区间第一根 K 线的日期")


class HengpanStock(BaseModel):
    code: str = Field(description="证券代码，如 sh.600000")
    name: str = Field(description="证券名称")
    industry: str = Field("未知行业", description="所属行业")
    is_st: bool = Field(description="扫描日是否为 ST")
    date: str = Field(description="末端 K 线时间；日线为日期，60 分钟线包含时间")
    close: float = Field(description="末端 K 线收盘价")
    amplitude: float = Field(description="末端振幅 (high - low) / close")
    matches: Dict[str, HengpanMatch] = Field(
        description="按规则编号给出的命中结果，只包含实体口径通过的规则组")
    kline_data: List[HengpanKline] = Field(description="所选周期的 K 线数据，已删除停牌行")


class HengpanSkipped(BaseModel):
    stale: int = Field(0, description="扫描日没有交易：停牌、未上市或数据源还没更新")
    insufficient: int = Field(0, description="删掉停牌行后，有效 K 线不足任何一组规则的回验根数 + 1")
    failed: int = Field(0, description="重试后仍取数失败")
    suspended: int = Field(0, description="每组规则的回验窗口里都有停牌缺失的交易日，不做判定")


class HengpanRuleStat(BaseModel):
    analyzed: int = Field(0, description="有效 K 线够这组规则回验的只数")
    passed_full: int = Field(0, description="整体口径入选只数")
    passed_body: int = Field(0, description="实体口径入选只数")
    near: int = Field(0, description="末端振幅离十字星分界不超过 0.1 个百分点的只数；振幅模式的规则组恒为 0")
    rescued: int = Field(0, description="其中按原模式整体口径淘汰、换一种模式就能入选的只数")
    suspended: int = Field(0, description="回验窗口里有停牌缺失的交易日、这组规则不判定的只数")
    over_amplitude: int = Field(0, description="末端振幅超过振幅上限被淘汰的只数；只在振幅模式的规则组里可能大于 0")


class HengpanStats(BaseModel):
    scan_date: Optional[str] = Field(None, description="扫描日")
    skipped: HengpanSkipped = Field(description="跳过只数，按原因分类")
    truncated: int = Field(0, description="命中但超出返回上限、未包含在结果里的只数；统计数字仍是真实值")
    rules: Dict[str, HengpanRuleStat] = Field(description="按规则编号给出的统计，不受返回上限影响")


class HengpanTaskCreated(BaseModel):
    task_id: str = Field(description="任务 ID，用于查询进度")
    message: str = Field(description="提示信息")


class HengpanStatusResponse(BaseModel):
    task_id: str = Field(description="任务 ID")
    status: str = Field(description="任务状态：pending 等待 / running 进行中 / completed 完成 / cancelled 已停止 / failed 失败")
    progress: int = Field(description="进度百分比，0-100")
    message: str = Field(description="当前进度说明")
    cancel_requested: bool = Field(
        False,
        description="是否已收到停止请求，任务仍会等待后台安全收口"
    )
    scan_date: Optional[str] = Field(None, description="扫描日，确定之前为空")
    frequency: str = Field("60", description="本次扫描周期：60 或 d")
    rules: Optional[List[HengpanRuleInfo]] = Field(None, description="本次扫描使用的规则组")
    stats: Optional[HengpanStats] = Field(None, description="统计，扫描过程中持续更新")
    result: Optional[List[HengpanStock]] = Field(None, description="全部入选股，任务结束后返回")
    new_results: Optional[List[HengpanStock]] = Field(None, description="本次新找到的股票，配合 cursor 边扫边出")
    cursor: int = Field(0, description="下次请求应传入的 since 值：已输出结果的累计条数")
    scanned: int = Field(0, description="已分析股票只数")
    total: int = Field(0, description="本次待分析股票只数")
    found: int = Field(0, description="已返回的股票只数（至少命中一组规则）")
    error: Optional[str] = Field(None, description="失败时的错误详情")
    created_at: float = Field(description="创建时间（Unix 时间戳，秒）")
    updated_at: float = Field(description="最近更新时间（Unix 时间戳，秒）")
    completed_at: Optional[float] = Field(None, description="结束时间（Unix 时间戳，秒）")


@router.post("/hengpan/scan/start", response_model=HengpanTaskCreated,
             summary="发起横盘选股",
             description="在后台按末端锚定横盘箱体规则扫描股票池，立即返回任务 ID，之后用「查询横盘选股进度」轮询。"
                         "可以一次给多组规则：取数只做一次，每只股票按各组规则分别判定，耗时与只扫一组相同。")
async def start_hengpan_scan(request: HengpanScanRequest, background_tasks: BackgroundTasks):
    params = request.model_dump()
    if params["scan_date"]:
        try:
            day = datetime.strptime(params["scan_date"], "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=422, detail="扫描日不是有效日期，格式应为 YYYY-MM-DD")
        if day > datetime.now().date():
            raise HTTPException(status_code=422, detail="扫描日不能晚于今天")

    rules = validate_rules(params["rules"])

    print(f"{Fore.CYAN}Starting anchored box scan task: {params}{Style.RESET_ALL}")
    task_id = task_manager.create_task()
    _extras[task_id] = {"params": params, "rules": rules, "scan_date": params["scan_date"],
                        "frequency": params["frequency"], "stats": None}
    background_tasks.add_task(_run_scan, task_id, params, rules)
    message = ("横盘选股任务已创建，正在读取本地 60 分钟行情…"
               if params["frequency"] == "60" else "横盘选股任务已创建，正在连接数据源…")
    return HengpanTaskCreated(task_id=task_id, message=message)


def _run_scan(task_id: str, params: Dict, rules: List[Dict]) -> None:
    """后台执行一次扫描：确定扫描日 → 准备股票池 → 逐只按各组规则分析 → 写入结果和历史快照。"""
    extras = _extras[task_id]
    try:
        task_manager.update_task(task_id, status=TaskStatus.RUNNING,
                                 message=("正在读取本地 60 分钟数据…" if params["frequency"] == "60"
                                          else "正在连接 Baostock 数据源…"))
        local_db_path = None
        if params["frequency"] == "60":
            with store_db.open_db() as conn:
                stock_list = store_db.stock_list_with_kline(
                    conn, "60", params["markets"] or store_db.DEFAULT_BOARDS)
                if not stock_list:
                    raise ValueError("本地股票池或 60 分钟行情为空，请先在「数据管理」页完成同步")
                selected_boards = list(dict.fromkeys(stock["board"] for stock in stock_list))
                latest = local_latest_date(conn, selected_boards, [stock["code"] for stock in stock_list])
                if not latest:
                    raise ValueError("所选板块没有本地 60 分钟线，请先同步行情数据")
                scan_date = params["scan_date"] or latest
                if params["scan_date"] and not store_db.has_kline_date(
                        conn, scan_date, "60", selected_boards):
                    raise ValueError(f"本地没有 {scan_date} 的 60 分钟数据，当前最新日期为 {latest}")
                local_db_path = store_db.DB_PATH
        else:
            with BaostockConnectionManager():
                task_manager.update_task(task_id, progress=2, message="正在获取所选板块的股票列表…")
                stock_basics_df = fetch_stock_basics()
                task_manager.update_task(task_id, progress=5, message="已获取股票列表，正在获取行业分类…")
                try:
                    industry_df = fetch_industry_data()
                except Exception as e:
                    print(f"{Fore.YELLOW}Warning: Failed to fetch industry data: {e}{Style.RESET_ALL}")
                    industry_df = pd.DataFrame()

                stock_list = select_markets(select_stocks(stock_basics_df, industry_df), params["markets"])
                if not stock_list:
                    raise ValueError("所选板块没有匹配的股票，请检查扫描范围")
                task_manager.update_task(task_id, progress=8, total=len(stock_list),
                                         message="正在确定所选周期的最新扫描日…")
                scan_date = resolve_scan_date(
                    params["scan_date"], frequency=params["frequency"],
                    probe_codes=[stock["code"] for stock in stock_list],
                )
        extras["scan_date"] = scan_date
        extras["stats"] = new_stats(scan_date, rules)
        # 交易日历用来识别回验窗口里的停牌缺口；本地还没同步过日历时为空，跳过这项检查
        with store_db.open_db() as conn:
            trading_days = store_db.trading_days(conn, end=scan_date) or None
        task_manager.update_task(task_id, progress=15, total=len(stock_list),
                                 message=f"扫描日 {scan_date}，已准备 {len(stock_list)} 只股票，开始逐只分析…")

        def update_progress(scanned, total, found, message):
            task_manager.update_task(task_id, progress=15 + int(scanned / total * 80),
                                     scanned=scanned, total=total, found=found, message=message)

        stocks = scan_anchored_box(
            stock_list, rules, params, scan_date, extras["stats"],
            update_progress=update_progress,
            frequency=params["frequency"],
            local_db_path=local_db_path,
            trading_days=trading_days,
            should_cancel=lambda: task_manager.is_cancel_requested(task_id),
            on_found=lambda item: task_manager.append_streamed(task_id, [item]))

        cancelled = task_manager.is_cancel_requested(task_id)
        stats = extras["stats"]
        summary = "、".join(f"{rule['id']} 组 {stats['rules'][rule['id']]['passed_full']} 只" for rule in rules)
        truncated = f"（命中 {len(stocks) + stats['truncated']} 只，超出上限的 {stats['truncated']} 只未返回）" \
            if stats["truncated"] else ""
        task_manager.update_task(
            task_id,
            status=TaskStatus.CANCELLED if cancelled else TaskStatus.COMPLETED,
            progress=100,
            message=(f"已停止扫描，保留停止前找到的 {len(stocks)} 只{truncated}" if cancelled else
                     f"扫描完成：返回 {len(stocks)} 只{truncated}，整体口径入选 {summary}"),
            result=stocks)
    except Exception as e:
        print(f"{Fore.RED}Error in anchored box scan: {e}{Style.RESET_ALL}")
        traceback.print_exc()
        # 标题给中文结论，原始异常和堆栈放进 error 供排查
        if isinstance(e, ConnectionError) and params["frequency"] == "60":
            summary = f"扫描失败：本地 60 分钟行情读取异常：{e}"
        elif isinstance(e, ConnectionError):
            summary = "扫描失败：无法从 Baostock 获取数据，可在「数据管理」页检查数据源连通性"
        elif isinstance(e, ValueError):
            summary = f"扫描失败：{e}"
        else:
            summary = "扫描失败：后端处理出错，详见错误详情"
        task_manager.update_task(task_id, status=TaskStatus.FAILED, message=summary,
                                 error=f"{e}\n{traceback.format_exc()}")
        return

    # 快照写失败只影响历史回看，不把已经完成的扫描标成失败
    task = task_manager.get_task(task_id)
    try:
        save_history(task_id, {
            "task_id": task_id,
            "status": task.status.value,
            "message": task.message,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
            "scan_date": extras["scan_date"],
            "frequency": params["frequency"],
            "params": params,
            "rules": rules,
            "stats": extras["stats"],
            "scanned": task.scanned,
            "total": task.total,
            "found": task.found,
            "results": stocks,
        })
    except Exception as e:
        print(f"{Fore.YELLOW}Warning: failed to save anchored box history {task_id}: {e}{Style.RESET_ALL}")


@router.get("/hengpan/scan/status/{task_id}", response_model=HengpanStatusResponse,
            summary="查询横盘选股进度",
            description="返回任务状态、进度、边扫边出的新结果和统计；任务结束后 result 为全部入选股。建议每 2 秒查询一次。",
            responses={404: {"description": "任务不存在（后端重启后进行中的任务会丢失）"}})
async def get_hengpan_status(
        task_id: str = Path(description="发起扫描时返回的任务 ID"),
        since: int = Query(0, ge=0, description="已收到的结果条数，只返回这之后的新结果")):
    task = task_manager.get_task(task_id)
    extras = _extras.get(task_id)
    if not task or extras is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
    return {**task.to_dict(since=since), "scan_date": extras["scan_date"],
            "frequency": extras.get("frequency", "d"),
            "rules": extras["rules"], "stats": extras["stats"]}


@router.post("/hengpan/scan/cancel/{task_id}",
             summary="停止横盘选股",
             description="请求停止进行中的扫描。已找到的结果会保留，状态变为 cancelled。",
             responses={404: {"description": "任务不存在或已结束"}})
async def cancel_hengpan_scan(task_id: str = Path(description="要停止的任务 ID")):
    if task_id not in _extras or not task_manager.request_cancel(task_id):
        raise HTTPException(status_code=404, detail="任务不存在，或已经结束")
    return {"success": True, "message": "已请求停止，正在收尾…"}


@router.get("/hengpan/scan/history",
            summary="横盘选股历史列表",
            description="只返回元数据；完整结果用「横盘选股历史详情」读取。")
async def get_hengpan_history_list():
    return {"histories": list_histories()}


@router.delete("/hengpan/scan/history/{history_id}",
              summary="删除横盘选股历史",
              description="删除一份历史扫描快照。",
              responses={404: {"description": "历史记录不存在"}})
async def delete_hengpan_history(history_id: str = Path(description="历史扫描 ID")):
    if not delete_history(history_id):
        raise HTTPException(status_code=404, detail=f"历史记录不存在：{history_id}")
    return {"history_id": history_id, "deleted": True}


@router.post("/hengpan/scan/history/cleanup",
             summary="清理横盘选股历史",
             description="按保留数量或保留天数清理历史扫描快照，两种策略二选一。")
async def cleanup_hengpan_history(request: HengpanHistoryCleanupRequest):
    if (request.keep_count is None) == (request.keep_days is None):
        raise HTTPException(status_code=422, detail="keep_count 和 keep_days 必须二选一")
    return cleanup_histories(keep_count=request.keep_count, keep_days=request.keep_days)


@router.get("/hengpan/scan/history/{history_id}",
            summary="横盘选股历史详情",
            description="返回一次扫描的参数、统计和全部入选股。",
            responses={404: {"description": "历史记录不存在"}})
async def get_hengpan_history_detail(history_id: str = Path(description="历史扫描 ID")):
    snapshot = get_history(history_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"历史记录不存在：{history_id}")
    return snapshot
