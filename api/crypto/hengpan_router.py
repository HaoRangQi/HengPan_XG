"""
横盘-U 接口：发起扫描、查询进度、停止扫描、历史快照。

和横盘-A（api/hengpan/router.py）一一对应，规则定义、校验、快照存储都直接复用那边的实现，
只把股票池换成本地加密币池、板块换成加密类别、周期固定在 1 小时线。
任务状态复用 api/task_manager.py；扫描日和统计存在本模块的 _extras 里。
"""
import traceback
from datetime import datetime
from typing import Dict, List, Optional

from colorama import Fore, Style
from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..hengpan.router import HengpanMatch, HengpanRule, HengpanRuleInfo, validate_rules
from ..task_manager import TaskStatus, task_manager, TaskExtras
from . import db
from .hengpan_history import (cleanup_histories, delete_history, get_history, list_histories,
                             save_history)
from .hengpan_scan import INTERVAL, has_kline_on, latest_scan_date, new_stats, scan_hengpan

router = APIRouter()

# task_id -> {"params", "rules", "scan_date", "stats"}；只记录本页面发起的任务
_extras = TaskExtras("hengpan_u")


class CryptoHengpanScanRequest(BaseModel):
    """横盘-U 扫描参数。多组规则共用一次取数，耗时与只扫一组相同。"""
    rules: List[HengpanRule] = Field(default_factory=lambda: [HengpanRule()], min_length=1, max_length=6,
                                     description="箱体规则，可同时给 1~6 组，结果按组分别标注；与横盘-A 完全同一套参数")
    scan_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$",
                                     description="扫描日 YYYY-MM-DD（北京时间），取该日最后一根 1 小时线作为末端；"
                                                 "留空取本地行情最新一天")
    categories: List[str] = Field(
        default_factory=list,
        description="只扫描指定类别：perpetual 加密永续 / tradifi TradFi 永续；留空为全部")
    min_quote_volume: float = Field(
        0, ge=0, description="24 小时成交额（USDT）门槛，低于它的交易对不扫；0 表示不限")


class CryptoHengpanHistoryCleanupRequest(BaseModel):
    """历史快照清理策略；按数量和按天数二选一。"""
    keep_count: Optional[int] = Field(None, ge=0, le=1000, description="保留最新的快照数量，0 清空非置顶记录")
    keep_days: Optional[int] = Field(None, ge=0, le=3650, description="保留最近多少天的快照，0 清空非置顶记录")


class CryptoHengpanKline(BaseModel):
    date: str = Field(description="北京时间 YYYY-MM-DD HH:MM:SS")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    close: Optional[float] = Field(None, description="收盘价")
    volume: Optional[float] = Field(None, description="成交量（币）")
    amount: Optional[float] = Field(None, description="成交额（USDT）")


class CryptoHengpanMatch(HengpanMatch):
    """一个交易对在某一组规则下的判定结果。上轨下轨按规则各不相同，所以逐组给出。"""
    mode: str = Field(description="命中模式：doji 十字星 / normal 普通 K 线 / amplitude 振幅模式 / "
                                  "tolerant 容刺箱体")
    amplitude: float = Field(description="末端振幅 (high - low) / close")
    upper: float = Field(description="箱体上轨")
    lower: float = Field(description="箱体下轨")
    actual_range: Optional[float] = Field(
        None, description="该规则回验区间加末端 K 线的实际震荡幅度：(最高价 - 最低价) / 最低价")
    over_amplitude: bool = Field(False, description="末端振幅超过这组规则的振幅上限，直接淘汰；只在振幅模式下可能为真")
    breach_full: int = Field(description="整体口径越界根数：最高价高于上轨或最低价低于下轨")
    breach_body: int = Field(description="实体口径越界根数：只看开盘价和收盘价")
    longest_consecutive_breach: Optional[int] = Field(
        None, description="最长连续实体刺破根数；只对 tolerant 模式返回")
    passed_full: bool = Field(description="整体口径下是否入选（默认口径）")
    passed_body: bool = Field(description="实体口径下是否入选")
    avg_amount: Optional[float] = Field(None, description="回验区间平均成交额（USDT）")
    avg_trades: Optional[float] = Field(
        None, description="回验区间平均成交笔数；加密没有换手率，用它衡量活跃度")
    lookback_start: Optional[str] = Field(None, description="回验区间第一根 K 线的时间")


class CryptoHengpanSymbol(BaseModel):
    symbol: str = Field(description="交易对，如 BTCUSDT")
    base_asset: str = Field(description="基础资产，如 BTC")
    category: str = Field(description="类别：perpetual / tradifi")
    category_label: str = Field(description="类别中文名")
    quote_volume: float = Field(0, description="24 小时成交额（USDT）")
    last_price: Optional[str] = Field(None, description="最新价")
    price_change_percent: Optional[str] = Field(None, description="24 小时涨跌幅（%）")
    date: str = Field(description="末端 K 线时间（北京时间）")
    close: float = Field(description="末端 K 线收盘价")
    amplitude: float = Field(description="末端振幅 (high - low) / close")
    matches: Dict[str, CryptoHengpanMatch] = Field(
        description="按规则编号给出的命中结果，只包含实体口径通过的规则组")
    kline_data: List[CryptoHengpanKline] = Field(description="1 小时 K 线数据")


class CryptoHengpanSkipped(BaseModel):
    stale: int = Field(0, description="扫描日没有 K 线：已下架、还没上架或本地没同步到这一天")
    insufficient: int = Field(0, description="本地 K 线不足任何一组规则的回验根数 + 1")
    failed: int = Field(0, description="读取本地行情失败")
    gap: int = Field(0, description="每组规则的回验窗口里都缺 K 线，不做判定")


class CryptoHengpanRuleStat(BaseModel):
    analyzed: int = Field(0, description="K 线够这组规则回验的交易对数")
    passed_full: int = Field(0, description="整体口径入选个数")
    passed_body: int = Field(0, description="实体口径入选个数")
    near: int = Field(0, description="末端振幅离十字星分界不超过 0.1 个百分点的个数；振幅模式恒为 0")
    rescued: int = Field(0, description="其中按原模式整体口径淘汰、换一种模式就能入选的个数")
    gap: int = Field(0, description="回验窗口里缺 K 线、这组规则不判定的个数")
    over_amplitude: int = Field(0, description="末端振幅超过振幅上限被淘汰的个数；只有振幅模式可能大于 0")


class CryptoHengpanStats(BaseModel):
    scan_date: Optional[str] = Field(None, description="扫描日")
    skipped: CryptoHengpanSkipped = Field(description="跳过个数，按原因分类")
    truncated: int = Field(0, description="命中但超出返回上限、未包含在结果里的个数；统计数字仍是真实值")
    rules: Dict[str, CryptoHengpanRuleStat] = Field(description="按规则编号给出的统计，不受返回上限影响")


class CryptoHengpanTaskCreated(BaseModel):
    task_id: str = Field(description="任务 ID，用于查询进度")
    message: str = Field(description="提示信息")


class CryptoHengpanStatusResponse(BaseModel):
    task_id: str = Field(description="任务 ID")
    status: str = Field(description="任务状态：pending / running / completed / cancelled / failed")
    progress: int = Field(description="进度百分比，0-100")
    message: str = Field(description="当前进度说明")
    cancel_requested: bool = Field(False, description="是否已收到停止请求，任务仍会等待后台安全收口")
    scan_date: Optional[str] = Field(None, description="扫描日，确定之前为空")
    frequency: str = Field(INTERVAL, description="本次扫描周期，固定 1h")
    rules: Optional[List[HengpanRuleInfo]] = Field(None, description="本次扫描使用的规则组")
    stats: Optional[CryptoHengpanStats] = Field(None, description="统计，扫描过程中持续更新")
    result: Optional[List[CryptoHengpanSymbol]] = Field(None, description="全部入选交易对，任务结束后返回")
    new_results: Optional[List[CryptoHengpanSymbol]] = Field(
        None, description="本次新找到的交易对，配合 cursor 边扫边出")
    cursor: int = Field(0, description="下次请求应传入的 since 值：已输出结果的累计条数")
    scanned: int = Field(0, description="已分析交易对个数")
    total: int = Field(0, description="本次待分析交易对个数")
    found: int = Field(0, description="已返回的交易对个数（至少命中一组规则）")
    error: Optional[str] = Field(None, description="失败时的错误详情")
    created_at: float = Field(description="创建时间（Unix 时间戳，秒）")
    updated_at: float = Field(description="最近更新时间（Unix 时间戳，秒）")
    completed_at: Optional[float] = Field(None, description="结束时间（Unix 时间戳，秒）")


@router.post("/crypto/hengpan/scan/start", response_model=CryptoHengpanTaskCreated,
             summary="发起横盘-U 扫描",
             description="在后台按末端锚定横盘箱体规则扫描本地加密币池，立即返回任务 ID，"
                         "之后用「查询横盘-U 进度」轮询。判定口径与横盘-A 完全一致，数据换成本地 1 小时线。")
async def start_crypto_hengpan_scan(request: CryptoHengpanScanRequest,
                                    background_tasks: BackgroundTasks):
    params = request.model_dump()
    if params["scan_date"]:
        try:
            day = datetime.strptime(params["scan_date"], "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=422, detail="扫描日不是有效日期，格式应为 YYYY-MM-DD")
        if day > datetime.now().date():
            raise HTTPException(status_code=422, detail="扫描日不能晚于今天")

    unknown = set(params["categories"]) - set(db.CATEGORIES)
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知加密类别：{', '.join(sorted(unknown))}")

    rules = validate_rules(params["rules"])

    print(f"{Fore.CYAN}Starting crypto anchored box scan task: {params}{Style.RESET_ALL}")
    task_id = task_manager.create_task()
    _extras[task_id] = {"params": params, "rules": rules, "scan_date": params["scan_date"],
                        "stats": None}
    background_tasks.add_task(_run_scan, task_id, params, rules)
    return CryptoHengpanTaskCreated(task_id=task_id,
                                    message="横盘-U 扫描任务已创建，正在读取本地 1 小时行情…")


def _run_scan(task_id: str, params: Dict, rules: List[Dict]) -> None:
    """后台执行一次扫描：准备币池 → 确定扫描日 → 逐个按各组规则分析 → 写入结果和历史快照。"""
    extras = _extras[task_id]
    try:
        task_manager.update_task(task_id, status=TaskStatus.RUNNING,
                                 message="正在读取本地加密币池…")
        categories = params["categories"] or list(db.CATEGORIES)
        with db.open_db() as conn:
            symbols = db.symbol_pool(conn, categories,
                                     min_quote_volume=params["min_quote_volume"])
            if not symbols:
                raise ValueError("所选类别没有符合条件的本地交易对，请先在「数据管理」页同步加密行情，"
                                 "或把 24 小时成交额门槛调低")
            latest = latest_scan_date(conn, categories)
            if not latest:
                raise ValueError("所选类别没有本地 1 小时线，请先在「数据管理」页同步加密行情")
            scan_date = params["scan_date"] or latest
            if params["scan_date"] and not has_kline_on(conn, scan_date, categories):
                raise ValueError(f"本地没有 {scan_date} 的 1 小时线，当前最新日期为 {latest}")

            extras["scan_date"] = scan_date
            extras["stats"] = new_stats(scan_date, rules)
            task_manager.update_task(
                task_id, progress=5, total=len(symbols),
                message=f"扫描日 {scan_date}，已准备 {len(symbols)} 个交易对，开始逐个分析…")

            def update_progress(scanned, total, found, message):
                task_manager.update_task(task_id, progress=5 + int(scanned / total * 90),
                                         scanned=scanned, total=total, found=found, message=message)

            results = scan_hengpan(
                conn, symbols, rules, scan_date, extras["stats"],
                update_progress=update_progress,
                should_cancel=lambda: task_manager.is_cancel_requested(task_id),
                on_found=lambda item: task_manager.append_streamed(task_id, [item]))

        cancelled = task_manager.is_cancel_requested(task_id)
        stats = extras["stats"]
        summary = "、".join(f"{rule['id']} 组 {stats['rules'][rule['id']]['passed_full']} 个"
                           for rule in rules)
        truncated = f"（命中 {len(results) + stats['truncated']} 个，超出上限的 {stats['truncated']} 个未返回）" \
            if stats["truncated"] else ""
        task_manager.update_task(
            task_id,
            status=TaskStatus.CANCELLED if cancelled else TaskStatus.COMPLETED,
            progress=100,
            message=(f"已停止扫描，保留停止前找到的 {len(results)} 个{truncated}" if cancelled else
                     f"扫描完成：返回 {len(results)} 个{truncated}，整体口径入选 {summary}"),
            result=results)
    except Exception as e:
        print(f"{Fore.RED}Error in crypto anchored box scan: {e}{Style.RESET_ALL}")
        traceback.print_exc()
        if isinstance(e, (ConnectionError, ValueError)):
            summary = f"扫描失败：{e}"
        else:
            summary = "扫描失败：后端处理出错，详见错误详情"
        task_manager.update_task(task_id, status=TaskStatus.FAILED, message=summary,
                                 error=f"{e}\n{traceback.format_exc()}")

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
            "frequency": INTERVAL,
            "params": params,
            "rules": rules,
            "stats": extras["stats"],
            "scanned": task.scanned,
            "total": task.total,
            "found": task.found,
            "results": task.result if task.result is not None else task.streamed,
            "error": task.error,
        })
    except Exception as e:
        task_manager.get_task(task_id).history_error = str(e)
        task_manager.get_task(task_id).checkpoint()
        print(f"{Fore.YELLOW}Warning: failed to save crypto anchored box history {task_id}: "
              f"{e}{Style.RESET_ALL}")


@router.get("/crypto/hengpan/scan/status/{task_id}", response_model=CryptoHengpanStatusResponse,
            summary="查询横盘-U 进度",
            description="返回任务状态、进度、边扫边出的新结果和统计；任务结束后 result 为全部入选交易对。"
                        "建议每 2 秒查询一次。",
            responses={404: {"description": "任务不存在（后端重启后进行中的任务会丢失）"}})
async def get_crypto_hengpan_status(
        task_id: str = Path(description="发起扫描时返回的任务 ID"),
        since: int = Query(0, ge=0, description="已收到的结果条数，只返回这之后的新结果"), compact: bool = Query(False)):
    task = task_manager.get_task(task_id)
    extras = _extras.get(task_id)
    if not task or extras is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
    base = task_manager.payload(task_id, since=since, compact=compact is True)
    if base is None:
        raise HTTPException(404, "任务缓存已过期，请从历史查看")
    payload = {**base, "scan_date": extras["scan_date"],
            "frequency": INTERVAL, "rules": extras["rules"], "stats": extras["stats"]}
    if compact is True:
        from fastapi.responses import JSONResponse
        return JSONResponse(payload)
    return payload


@router.post("/crypto/hengpan/scan/cancel/{task_id}",
             summary="停止横盘-U 扫描",
             description="请求停止进行中的扫描。已找到的结果会保留，状态变为 cancelled。",
             responses={404: {"description": "任务不存在或已结束"}})
async def cancel_crypto_hengpan_scan(task_id: str = Path(description="要停止的任务 ID")):
    if task_id not in _extras or not task_manager.request_cancel(task_id):
        raise HTTPException(status_code=404, detail="任务不存在，或已经结束")
    return {"success": True, "message": "已请求停止，正在收尾…"}


@router.get("/crypto/hengpan/scan/history",
            summary="横盘-U 历史列表",
            description="只返回元数据；完整结果用「横盘-U 历史详情」读取。")
async def get_crypto_hengpan_history_list():
    return {"histories": list_histories()}


@router.delete("/crypto/hengpan/scan/history/{history_id}",
               summary="删除横盘-U 历史",
               description="删除一份历史扫描快照。",
               responses={404: {"description": "历史记录不存在"}})
async def delete_crypto_hengpan_history(history_id: str = Path(description="历史扫描 ID")):
    if not delete_history(history_id):
        raise HTTPException(status_code=404, detail=f"历史记录不存在：{history_id}")
    return {"history_id": history_id, "deleted": True}


@router.post("/crypto/hengpan/scan/history/cleanup",
             summary="清理横盘-U 历史",
             description="按保留数量或保留天数清理历史扫描快照，两种策略二选一。")
async def cleanup_crypto_hengpan_history(request: CryptoHengpanHistoryCleanupRequest):
    if (request.keep_count is None) == (request.keep_days is None):
        raise HTTPException(status_code=422, detail="keep_count 和 keep_days 必须二选一")
    return cleanup_histories(keep_count=request.keep_count, keep_days=request.keep_days)


@router.get("/crypto/hengpan/scan/history/{history_id}",
            summary="横盘-U 历史详情",
            description="返回一次扫描的参数、统计和全部入选交易对。",
            responses={404: {"description": "历史记录不存在"}})
async def get_crypto_hengpan_history_detail(history_id: str = Path(description="历史扫描 ID")):
    snapshot = get_history(history_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"历史记录不存在：{history_id}")
    return snapshot
