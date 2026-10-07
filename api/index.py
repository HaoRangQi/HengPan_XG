# api/index.py
from colorama import Fore, Style
import colorama  # For colored console output
import traceback
import math
import pandas as pd
from typing import List, Dict, Optional
from .scan_parameters import ScanParameters
from pydantic import BaseModel, Field, RootModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, BackgroundTasks, Path, Query
import sys
import os

# 添加当前目录到 Python 路径，以便导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Import our modular components (using absolute imports)
try:
    from api.config import ScanConfig
    from api.task_manager import task_manager, TaskStatus
    from api.data_fetcher import fetch_stock_basics, fetch_industry_data, BaostockConnectionManager
    from api.platform_scanner import prepare_stock_list, scan_stocks, select_markets
    from api.platform_scan_source import prepare_platform_scan_source
    from api.case_api import router as case_router
    from api.data_api import router as data_router
    from api.scan_history import save_scan_history, list_scan_histories, get_scan_history
    from api.hengpan.router import router as hengpan_router
    from api.store.router import router as store_router
    from api.crypto.router import router as crypto_router
    from api.crypto.platform_router import router as crypto_platform_router
    from api.crypto.hengpan_router import router as crypto_hengpan_router
    from api.history.router import router as history_router
except ImportError:
    # 如果绝对导入失败，尝试相对导入（本地开发环境）
    from .config import ScanConfig
    from .task_manager import task_manager, TaskStatus
    from .data_fetcher import fetch_stock_basics, fetch_industry_data, BaostockConnectionManager
    from .platform_scanner import prepare_stock_list, scan_stocks, select_markets
    from .platform_scan_source import prepare_platform_scan_source
    from .case_api import router as case_router
    from .data_api import router as data_router
    from .scan_history import save_scan_history, list_scan_histories, get_scan_history
    from .hengpan.router import router as hengpan_router
    from .store.router import router as store_router
    from .crypto.router import router as crypto_router
    from .crypto.platform_router import router as crypto_platform_router
    from .crypto.hengpan_router import router as crypto_hengpan_router
    from .history.router import router as history_router


# Define request body model using Pydantic
class ScanConfigRequest(ScanParameters):
    """Request model for stock platform scan configuration."""
    # Window settings - 基于平台期分析的最佳参数组合
    windows: List[int] = Field(default_factory=lambda: [20, 30, 60],
                               description="窗口期（K线根数），可同时分析多个，未传时为 [20, 30, 60]")
    frequency: str = Field("d", pattern="^(d|60)$", description="K线频率：d 日线或 60 分钟线")
    data_source: str = Field(
        "baostock", pattern="^(local|baostock)$",
        description="行情来源：local 本地库；baostock 旧版联网。缺省保持旧版兼容。")

    # Price pattern thresholds - 适合识别安记食品类型的平台期
    box_threshold: float = Field(0.5, description="振幅阈值：窗口内价格最大振幅比例，0.3 即 30%")
    ma_diff_threshold: float = Field(0.03, description="均线粘合度：各均线之间的最大偏离比例")
    volatility_threshold: float = Field(0.09, description="波动率阈值：日间波动上限")  # 从0.04调整到0.09，以便更好地识别平台期

    # Volume analysis settings - 适合平台期
    use_volume_analysis: bool = Field(True, description="是否启用成交量分析（要求横盘期缩量）")
    # Maximum volume change ratio for consolidation
    volume_change_threshold: float = Field(0.9, description="成交量变化阈值：横盘期内成交量变化的最大比例")
    # Maximum volume stability for consolidation
    volume_stability_threshold: float = Field(0.75, description="成交量稳定性阈值：横盘期内成交量波动的最大程度")  # 从0.7调整到0.75，以便在20天窗口也能识别出平台期
    # Minimum volume increase ratio for breakthrough
    volume_increase_threshold: float = Field(1.5, description="成交量突破阈值：放量达到该倍数视为突破")

    # Technical indicators
    use_technical_indicators: bool = Field(False, description="保留字段，当前未使用")  # Whether to use technical indicators
    # Whether to use breakthrough prediction
    use_breakthrough_prediction: bool = Field(False, description="是否启用突破前兆识别（只在入选理由中标注，不参与筛选）")

    # Position analysis settings
    use_low_position: bool = Field(True, description="是否启用低位判断（要求股价已从高点明显回落）")  # Whether to use low position analysis
    # Number of days to look back for finding the high point
    high_point_lookback_days: int = Field(365, alias="high_point_lookback_bars", description="高点查找窗口（K线根数）")
    # Number of days within which the decline should have occurred
    decline_period_days: int = Field(180, description="下跌时间范围（日历天）")
    # Minimum decline percentage from high to be considered at low position
    decline_threshold: float = Field(0.3, description="下跌幅度阈值：较高点的最小跌幅，0.3 即 30%")  # 从0.5降低到0.3，更符合实际情况

    # Rapid decline detection settings
    # Whether to use rapid decline detection
    use_rapid_decline_detection: bool = Field(True, description="是否启用快速下跌判断，仅在低位判断开启时生效")
    rapid_decline_days: int = Field(30, alias="rapid_decline_bars", description="快速下跌窗口（K线根数）")  # Number of days to define a rapid decline period
    # Minimum decline percentage within rapid_decline_days to be considered rapid
    rapid_decline_threshold: float = Field(0.15, description="快速下跌幅度阈值，0.15 即 15%")

    # Breakthrough confirmation settings
    # Whether to use breakthrough confirmation
    use_breakthrough_confirmation: bool = Field(False, description="是否启用突破确认（只在入选理由中标注，不参与筛选）")
    # Number of days to look for confirmation
    breakthrough_confirmation_days: int = Field(1, alias="breakthrough_confirmation_bars", description="突破后需要站稳的K线根数")

    # Box pattern detection settings
    use_box_detection: bool = Field(True, description="是否启用箱体检测（要求形成箱体，并标出支撑位与阻力位）")  # Whether to use box pattern detection
    # Minimum quality score for a valid box pattern
    box_quality_threshold: float = Field(0.6, description="箱体质量阈值：箱体形态的最低质量评分")

    # Fundamental analysis settings
    use_fundamental_filter: bool = Field(False, description="是否启用基本面筛选")  # 是否启用基本面筛选
    # 营收增长率行业百分位要求（值越小要求越严格，如0.3表示要求位于行业前30%）
    revenue_growth_percentile: float = Field(0.3, description="营收增长率需位于行业前 X，0.3 即前 30%")
    # 净利润增长率行业百分位要求（值越小要求越严格，如0.3表示要求位于行业前30%）
    profit_growth_percentile: float = Field(0.3, description="净利润增长率需位于行业前 X，0.3 即前 30%")
    # ROE行业百分位要求（值越小要求越严格，如0.3表示要求位于行业前30%）
    roe_percentile: float = Field(0.3, description="ROE 需位于行业前 X，0.3 即前 30%")
    # 资产负债率行业百分位要求（值越大要求越严格，如0.3表示要求位于行业后30%）
    liability_percentile: float = Field(0.3, description="资产负债率需位于行业后 X，0.3 即后 30%")
    # PE行业百分位要求（值越大要求越宽松，如0.7表示要求不在行业前30%最高估值）
    pe_percentile: float = Field(0.7, description="PE 百分位：0.7 表示排除行业估值最高的 30%")
    # PB行业百分位要求（值越大要求越宽松，如0.7表示要求不在行业前30%最高估值）
    pb_percentile: float = Field(0.7, description="PB 百分位：0.7 表示排除行业估值最高的 30%")
    # 检查连续增长的年数
    fundamental_years_to_check: int = Field(3, description="要求连续增长的年数")

    # Window weights
    use_window_weights: bool = Field(False, description="是否启用窗口权重（在入选理由中给出加权得分）")  # Whether to use window weights
    window_weights: Dict[int, float] = Field(
        default_factory=dict, description="各窗口期的权重，键为窗口期天数")  # Weights for different windows

    # Market / board filter
    markets: List[str] = Field(
        default_factory=list,
        description="只扫描指定板块，可选：sh_main 沪市主板 / sz_main 深市主板 / sz_gem 创业板 / sh_star 科创板 / bj 北交所；留空为全市场")

    # System settings
    max_workers: int = Field(5, description="并发拉取数据的进程数")  # Keep concurrency reasonable for serverless
    retry_attempts: int = Field(2, description="单只股票拉取失败时的重试次数")
    retry_delay: int = Field(1, description="重试间隔（秒）")
    # 期望返回的股票数量；传 null 表示不限制，返回全部符合条件的股票
    expected_count: Optional[int] = Field(
        10, description="期望返回的股票数量，超出时按行业均衡挑选；传 null 不限制数量")

# --- Define response models ---


class SelectionReasons(RootModel[Dict[int, str]]):
    """Maps window sizes to selection reasons (descriptive text)"""
    pass


class KlineDataPoint(BaseModel):
    """Model for a single K-line data point."""
    date: str = Field(description="交易日期或分钟线时间")
    open: float | None = Field(None, description="开盘价（前复权）")  # Allow None for robustness
    high: float | None = Field(None, description="最高价")
    low: float | None = Field(None, description="最低价")
    close: float | None = Field(None, description="收盘价")
    volume: float | None = Field(None, description="成交量（股）")
    turn: float | None = Field(None, description="换手率（%）")
    preclose: float | None = Field(None, description="前收盘价")
    pctChg: float | None = Field(None, description="涨跌幅（%）")
    peTTM: float | None = Field(None, description="滚动市盈率")
    pbMRQ: float | None = Field(None, description="市净率")


class MarkLine(BaseModel):
    """Model for a marking line on a chart."""
    date: Optional[str] = Field(None, description="竖线所在交易日")
    text: str = Field(description="标记文字，如 高点、支撑位")
    color: str = Field(description="线条颜色")
    type: Optional[str] = Field(None, description="为 horizontal 时表示价格水平线")
    value: Optional[float] = Field(None, description="水平线对应的价格")


class StockScanResult(BaseModel):
    """Model for a stock that meets platform criteria."""
    code: str = Field(description="证券代码，如 sh.600000")
    name: str = Field(description="证券名称")
    industry: str | None = Field("未知行业", description="所属行业")
    selection_reasons: Dict[int, str] = Field(description="入选理由，键为窗口期天数")
    kline_data: List[KlineDataPoint] = Field(description="日线数据")
    mark_lines: Optional[List[MarkLine]] = Field(None, description="图上标记线：高点、下跌起止、支撑位与阻力位")

# --- Task-related models ---


class TaskCreationResponse(BaseModel):
    """Response model for task creation."""
    task_id: str = Field(description="任务 ID，用于查询进度")
    message: str = Field(description="提示信息")


class TaskStatusResponse(BaseModel):
    """Response model for task status."""
    task_id: str = Field(description="任务 ID")
    status: str = Field(description="任务状态：pending 等待 / running 进行中 / completed 完成 / cancelled 已停止 / failed 失败")
    progress: int = Field(description="进度百分比，0-100")
    message: str = Field(description="当前进度说明")
    result: Optional[List[StockScanResult]] = Field(None, description="扫描结果，任务完成后返回")
    new_results: Optional[List[StockScanResult]] = Field(
        None, description="本次新发现的股票，配合 cursor 使用可边扫边出")
    cursor: int = Field(0, description="下次请求应传入的 since 值：已输出结果的累计条数")
    scanned: int = Field(0, description="已分析股票只数")
    total: int = Field(0, description="本次待分析股票只数")
    found: int = Field(0, description="已发现平台期股票只数（未截断）")
    cancel_requested: bool = Field(False, description="是否已收到停止请求，任务仍会等后台安全收口")
    error: Optional[str] = Field(None, description="失败时的错误详情")
    created_at: float = Field(description="创建时间（Unix 时间戳，秒）")
    updated_at: float = Field(description="最近更新时间（Unix 时间戳，秒）")
    completed_at: Optional[float] = Field(None, description="结束时间（Unix 时间戳，秒）")


from contextlib import asynccontextmanager
import asyncio
from .task_api import router as task_router

@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(task_manager.recover)
    async def reap():
        while True:
            await asyncio.sleep(60)
            await asyncio.to_thread(task_manager.clean_old_tasks)
    reaper=asyncio.create_task(reap())
    try:yield
    finally:
        reaper.cancel()
        try:await reaper
        except asyncio.CancelledError:pass

# Initialize FastAPI app
app = FastAPI(
    lifespan=lifespan,
    title="股票平台期扫描 API",
    description="在全市场 A 股中扫描横盘整理（平台期）的股票，并提供案例管理与数据源查询接口。",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(task_router, prefix="/api", tags=["任务结果"])

# Include case management router
app.include_router(case_router, prefix="/api", tags=["案例管理"])

# Include data source catalog router
app.include_router(data_router, prefix="/api", tags=["数据管理"])

# Include 横盘选股 router
app.include_router(hengpan_router, prefix="/api", tags=["横盘选股"])

# Include local market storage router
app.include_router(store_router, prefix="/api", tags=["本地数据"])

# 加密货币行情，与 A 股完全分开
app.include_router(crypto_router, prefix="/api", tags=["加密行情"])
app.include_router(crypto_platform_router, prefix="/api", tags=["平台-U 扫描"])
app.include_router(crypto_hengpan_router, prefix="/api", tags=["横盘-U 扫描"])

# 四个扫描页共用的历史库
app.include_router(history_router, prefix="/api", tags=["扫描历史"])

# --- API Endpoints ---


@app.get("/", tags=["系统"], summary="健康检查", description="确认后端服务正在运行。")
async def root():
    """
    Root endpoint for health check.
    """
    return {
        "status": "ok",
        "message": "Stock Platform Scanner API is running",
        "version": "1.0.0"
    }


# OpenAPI 描述挂在 /api 下，前端经开发代理即可读取，用于中文接口文档页；原 /docs、/openapi.json 保留
@app.get("/api/openapi.json", include_in_schema=False)
def openapi_spec():
    return app.openapi()


@app.post("/api/scan/start", response_model=TaskCreationResponse, tags=["扫描任务"],
          summary="发起扫描任务",
          description="在后台启动全市场平台期扫描并立即返回任务 ID，之后用「查询扫描进度」轮询进度与结果。")
async def start_scan(config_request: ScanConfigRequest, background_tasks: BackgroundTasks):
    """
    Start a stock platform scan as a background task.
    Returns a task ID that can be used to check the status of the scan.
    """
    # Initialize colorama for colored console output
    colorama.init()

    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Starting stock platform scan task{Style.RESET_ALL}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")

    # Create a new task
    task_id = task_manager.create_task()
    task_manager.get_task(task_id).history_required = True

    # Convert request to config dictionary
    config_dict = config_request.model_dump()
    task_manager.get_task(task_id).metadata["platform_a"]={"params":config_dict}
    task_manager.get_task(task_id).checkpoint()
    print(f"{Fore.YELLOW}Scan configuration:{Style.RESET_ALL}")
    for key, value in config_dict.items():
        print(f"  - {key}: {Fore.GREEN}{value}{Style.RESET_ALL}")

    # Start the scan in the background
    def run_scan_task():
        try:
            data_source = config_dict.get("data_source", "baostock")
            is_local = data_source == "local"
            task_manager.update_task(
                task_id,
                status=TaskStatus.RUNNING,
                message="正在读取本地行情库…" if is_local else "正在连接 Baostock 数据源…"
            )
            task_manager.update_task(
                task_id,
                progress=5,
                message=("正在从本地库准备股票池…" if is_local
                         else "正在获取股票列表和行业分类…")
            )
            source = prepare_platform_scan_source(
                data_source,
                config_dict.get("markets"),
                config_dict.get("frequency", "d"),
                config_dict.get("use_fundamental_filter", False),
            )
            stock_list = source.stock_list
            task_manager.update_task(
                task_id,
                progress=30,
                total=len(stock_list),
                message=(
                    f"本地数据截至 {source.end_date}，已准备 {len(stock_list)} 只股票，开始分析…"
                    if is_local else
                    f"已准备 {len(stock_list)} 只股票，开始逐只联网取数并分析…"
                )
            )

            # 扫描过程中一旦发现平台期股票，立即转成响应模型并追加输出
            def on_found(stock):
                try:
                    result = build_result_stock(stock)
                    if result is not None:
                        task_manager.append_streamed(task_id, [result.model_dump()])
                        return {key: value for key, value in stock.items() if key != 'kline_data'}
                except Exception as exc:
                    print(f"{Fore.YELLOW}Warning: failed to stream result "
                          f"{stock.get('code')}: {exc}{Style.RESET_ALL}")

            # frequency/data_source are transport-only options; ScanConfig
            # remains compatible with older synchronous callers.
            scan_config = ScanConfig(**{
                key: value for key, value in config_dict.items()
                if key not in ("frequency", "data_source")
            })

            def update_progress(progress=None, message=None, scanned=None,
                                total=None, found=None):
                fields = {}
                if progress is not None and message is not None:
                    fields["progress"] = 30 + min(int(progress * 0.6), 60)
                if message is not None:
                    fields["message"] = message
                if scanned is not None:
                    fields["scanned"] = scanned
                if total is not None:
                    fields["total"] = total
                if found is not None:
                    fields["found"] = found
                if fields:
                    task_manager.update_task(task_id, **fields)

            platform_stocks = scan_stocks(
                stock_list,
                scan_config,
                update_progress,
                should_cancel=lambda: task_manager.is_cancel_requested(task_id),
                on_found=on_found,
                frequency=source.frequency,
                local_db_path=source.local_db_path,
                end_date=source.end_date,
            )

            # The callback already normalized and cached the full rows. Select
            # only the final filtered identities, without rebuilding every chart.
            task_manager.finish_results(task_id, platform_stocks)
            result_count = len(platform_stocks)

            cancel_requested = task_manager.is_cancel_requested(task_id)
            task_manager.update_task(
                task_id,
                status=TaskStatus.CANCELLED if cancel_requested else TaskStatus.COMPLETED,
                progress=100,
                message=(
                    f"已停止扫描，保留停止前扫到的 {result_count} 只股票"
                    if cancel_requested else
                    f"扫描完成，共 {result_count} 只股票符合条件"
                ),
            )

        except Exception as e:
            print(f"{Fore.RED}Error in scan task: {e}{Style.RESET_ALL}")
            traceback.print_exc()
            # 标题给中文结论，原始异常与堆栈放进 error 供排查
            if config_dict.get("data_source") == "local":
                summary = f"本地扫描失败：{e}"
            elif isinstance(e, ConnectionError):
                summary = "扫描失败：无法从 Baostock 获取数据，可在「数据管理」页检查数据源连通性"
            else:
                summary = "扫描失败：后端处理出错，详见错误详情"
            task_manager.update_task(
                task_id,
                status=TaskStatus.FAILED,
                message=summary,
                error=f"{e}\n{traceback.format_exc()}"
            )

        task = task_manager.get_task(task_id)
        try:
            save_scan_history(task_id, {
                "task_id": task_id, "status": task.status.value, "message": task.message,
                "error": task.error, "created_at": task.created_at, "completed_at": task.completed_at,
                "frequency": config_dict.get("frequency", "d"),
                "data_source": config_dict.get("data_source", "baostock"),
                "config": config_dict, "parameters": config_dict,
                "windows": config_dict.get("windows", []), "scanned": task.scanned,
                "total": task.total, "found": task.found,
                "results": task.result if task.result is not None else task.streamed,
            })
        except Exception as error:
            task_manager.get_task(task_id).history_error = str(error)
            task_manager.get_task(task_id).checkpoint()
            print(f"Warning: failed to save platform history {task_id}: {error}")

    # Start the task in the background
    background_tasks.add_task(run_scan_task)

    # Return task ID
    return TaskCreationResponse(
        task_id=task_id,
        message=("扫描任务已创建，正在读取本地行情库…"
                 if config_dict.get("data_source") == "local" else
                 "扫描任务已创建，正在连接旧版 Baostock 数据源…")
    )


def _format_kline_timestamp(date_value, time_value) -> str:
    date_text = str(date_value)
    # 本地 reader 已输出完整的 YYYY-MM-DD HH:MM:SS，不再拼接 time。
    if len(date_text) > 10 and " " in date_text:
        return date_text
    if time_value is None or str(time_value) in ('nan', 'None', ''):
        return date_text

    time_text = str(time_value).strip()
    if time_text.endswith('.0') and time_text[:-2].isdigit():
        time_text = time_text[:-2]

    # Baostock minute rows commonly use YYYYMMDDHHMMSSmmm; keep only the
    # intraday HHMMSS portion because the date column is already authoritative.
    if len(time_text) >= 14 and time_text[:8].isdigit():
        time_text = time_text[8:14]
    if time_text.isdigit() and len(time_text) <= 6:
        time_text = time_text.zfill(6)
        time_text = f'{time_text[:2]}:{time_text[2:4]}:{time_text[4:6]}'

    return f'{date_text} {time_text}'


def _optional_float(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def build_result_stock(stock: Dict) -> Optional[StockScanResult]:
    """把扫描结果转成响应模型；单只数据异常时返回 None 而不是中断整个任务。"""
    kline_data = []
    for point in stock.get('kline_data', []):
        try:
            point_time = point.get('time')
            point_date = _format_kline_timestamp(point.get('date'), point_time)
            kline_data.append(KlineDataPoint(
                date=point_date,
                open=_optional_float(point.get('open')),
                high=_optional_float(point.get('high')),
                low=_optional_float(point.get('low')),
                close=_optional_float(point.get('close')),
                volume=_optional_float(point.get('volume')),
                turn=_optional_float(point.get('turn')),
                preclose=_optional_float(point.get('preclose')),
                pctChg=_optional_float(point.get('pctChg')),
                peTTM=_optional_float(point.get('peTTM')),
                pbMRQ=_optional_float(point.get('pbMRQ')),
            ))
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Failed to process K-line data point: {e}{Style.RESET_ALL}")
            continue

    mark_lines = []
    for mark in stock.get('mark_lines', []) or []:
        try:
            mark_lines.append(MarkLine(**mark))
        except Exception as e:
            print(f"{Fore.YELLOW}Warning: Failed to process mark line: {e}{Style.RESET_ALL}")
            continue

    try:
        return StockScanResult(
            code=stock['code'],
            name=stock['name'],
            industry=stock.get('industry', '未知行业'),
            selection_reasons=stock.get('selection_reasons', {}),
            kline_data=kline_data,
            mark_lines=mark_lines,
        )
    except Exception as e:
        print(f"{Fore.RED}Error creating StockScanResult: {e}{Style.RESET_ALL}")
        return None


@app.post("/api/scan/cancel/{task_id}", tags=["扫描任务"],
          summary="停止扫描",
          description="请求停止进行中的扫描任务。已分析出的结果会保留，状态变为 cancelled。",
          responses={404: {"description": "任务不存在或已结束"}})
async def cancel_scan(task_id: str = Path(description="要停止的任务 ID")):
    task = task_manager.get_task(task_id)
    if not task or "platform_a" not in task.metadata or not task_manager.request_cancel(task_id):
        raise HTTPException(status_code=404, detail="任务不存在，或已经结束")
    return {"success": True, "message": "已请求停止，正在收尾…"}


@app.get("/api/scan/status/{task_id}", response_model=TaskStatusResponse, tags=["扫描任务"],
         summary="查询扫描进度",
         description="返回任务状态、进度与当前说明；任务完成后 result 字段包含扫描结果。建议每 2 秒查询一次。",
         responses={404: {"description": "任务不存在（后端重启后进行中的任务会丢失）"}})
async def get_scan_status(
        task_id: str = Path(description="发起扫描时返回的任务 ID"),
        since: int = Query(0, ge=0, description="已收到的结果条数，只返回这之后的新结果"), compact: bool = Query(False)):
    """
    Get the status of a scan task.
    """
    task = task_manager.get_task(task_id)
    if not task or "platform_a" not in task.metadata:
        raise HTTPException(
            status_code=404, detail=f"任务不存在：{task_id}")

    if compact is True:
        from fastapi.responses import JSONResponse
        return JSONResponse(task_manager.payload(task_id, since=since, compact=True))
    return task_manager.payload(task_id, since=since)


@app.get("/api/scan/history", tags=["扫描任务"], summary="扫描历史列表")
async def get_scan_history_list():
    """Return metadata only; use the detail endpoint for full K-line results."""
    return {"histories": list_scan_histories()}


@app.get("/api/scan/history/{history_id}", tags=["扫描任务"], summary="扫描历史详情")
async def get_scan_history_detail(history_id: str = Path(description="历史扫描 ID")):
    snapshot = get_scan_history(history_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"历史记录不存在：{history_id}")
    return snapshot

# Legacy endpoint for backward compatibility


@app.post("/api/scan", response_model=List[StockScanResult], tags=["扫描任务"],
          summary="同步扫描（旧接口）",
          description="阻塞到扫描结束后一次性返回结果，可能耗时数分钟，仅为兼容保留，新代码请用「发起扫描任务」。")
async def run_scan(config_request: ScanConfigRequest):
    """
    Legacy API endpoint for backward compatibility.
    This endpoint starts a scan and waits for it to complete.
    For long-running scans, use the /api/scan/start endpoint instead.
    """
    # Initialize colorama for colored console output
    colorama.init()

    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Legacy scan endpoint called{Style.RESET_ALL}")
    print(f"{Fore.CYAN}======================================{Style.RESET_ALL}")

    # Convert request to config dictionary
    config_dict = config_request.model_dump()

    # Create scan config
    scan_config = ScanConfig(**config_dict)

    # Fetch stock basics
    with BaostockConnectionManager():
        stock_basics_df = fetch_stock_basics()

        # Fetch industry data
        try:
            industry_df = fetch_industry_data()
        except Exception as e:
            print(
                f"{Fore.YELLOW}Warning: Failed to fetch industry data: {e}{Style.RESET_ALL}")
            industry_df = pd.DataFrame()

        # Prepare stock list
        stock_list = prepare_stock_list(stock_basics_df, industry_df)

        # Run the scan
        platform_stocks = scan_stocks(
            stock_list, scan_config, frequency=config_dict.get("frequency", "d"))

    # Process results for API response
    result_stocks = []
    for stock in platform_stocks:
        # Convert kline_data to KlineDataPoint objects
        kline_data = []
        for point in stock.get('kline_data', []):
            try:
                kline_point = {
                    'date': str(point.get('date')),
                    'open': float(point['open']) if point.get('open') is not None else None,
                    'high': float(point['high']) if point.get('high') is not None else None,
                    'low': float(point['low']) if point.get('low') is not None else None,
                    'close': float(point['close']) if point.get('close') is not None else None,
                    'volume': float(point['volume']) if point.get('volume') is not None else None,
                    'turn': float(point['turn']) if point.get('turn') is not None else None,
                    'preclose': float(point['preclose']) if point.get('preclose') is not None else None,
                    'pctChg': float(point['pctChg']) if point.get('pctChg') is not None else None,
                    'peTTM': float(point['peTTM']) if point.get('peTTM') is not None else None,
                    'pbMRQ': float(point['pbMRQ']) if point.get('pbMRQ') is not None else None,
                }
                kline_data.append(KlineDataPoint(**kline_point))
            except Exception as e:
                print(
                    f"{Fore.YELLOW}Warning: Failed to process K-line data point: {e}{Style.RESET_ALL}")
                continue

        # Create StockScanResult object
        try:
            # 处理标记线数据
            mark_lines = []
            if 'mark_lines' in stock:
                for mark in stock['mark_lines']:
                    try:
                        mark_lines.append(MarkLine(**mark))
                    except Exception as e:
                        print(
                            f"{Fore.YELLOW}Warning: Failed to process mark line: {e}{Style.RESET_ALL}")
                        continue

            result_stock = StockScanResult(
                code=stock['code'],
                name=stock['name'],
                industry=stock.get('industry', '未知行业'),
                selection_reasons=stock.get('selection_reasons', {}),
                kline_data=kline_data,
                mark_lines=mark_lines
            )
            result_stocks.append(result_stock)
        except Exception as e:
            print(f"{Fore.RED}Error creating StockScanResult: {e}{Style.RESET_ALL}")
            continue

    return result_stocks

# 添加测试API端点


@app.post("/api/scan/test", response_model=List[StockScanResult], tags=["扫描任务"],
          summary="返回模拟数据",
          description="不访问数据源，直接返回一只带标记线的模拟股票，用于调试前端。")
async def test_scan(config_request: ScanConfigRequest):
    """
    Test API endpoint that returns sample data with marking lines.
    This is useful for testing the frontend without running a full scan.
    """
    # 创建一个模拟的股票数据
    from datetime import datetime, timedelta
    import numpy as np

    # 生成日期序列
    end_date = datetime.now()
    dates = [(end_date - timedelta(days=i)).strftime('%Y-%m-%d')
             for i in range(200)]
    dates.reverse()  # 按时间顺序排列

    # 生成价格数据
    high_price = 30.0
    prices = []

    # 上涨阶段
    for i in range(50):
        prices.append(20 + i * 0.2)

    # 高点和下跌阶段
    for i in range(30):
        prices.append(high_price - i * 0.3)

    # 平台期
    platform_price = 20.0
    for i in range(100):
        # 在平台价格附近波动
        prices.append(platform_price + np.random.normal(0, 0.5))

    # 突破
    for i in range(20):
        prices.append(platform_price + 2 + i * 0.1)

    # 创建K线数据
    kline_data = []
    for i, date in enumerate(dates):
        if i < len(prices):
            price = prices[i]
            kline_point = {
                'date': date,
                'open': price - 0.2,
                'high': price + 0.5,
                'low': price - 0.5,
                'close': price + 0.2,
                'volume': 10000 + np.random.randint(0, 5000),
                'turn': 1.5,
                'preclose': price if i == 0 else prices[i-1],
                'pctChg': 0.5,
                'peTTM': 15.0,
                'pbMRQ': 2.0
            }
            kline_data.append(KlineDataPoint(**kline_point))

    # 创建标记线数据
    mark_lines = [
        MarkLine(date=dates[49], text="高点", color="#ec0000"),
        MarkLine(date=dates[50], text="开始下跌", color="#ec0000"),
        MarkLine(date=dates[80], text="平台期开始", color="#3b82f6"),
        MarkLine(date=dates[180], text="突破", color="#10b981")
    ]

    # 创建支撑位和阻力位
    support_level = platform_price - 0.5
    resistance_level = platform_price + 0.5

    mark_lines.append(MarkLine(type="horizontal",
                      value=support_level, text="支撑位", color="#10b981"))
    mark_lines.append(MarkLine(type="horizontal",
                      value=resistance_level, text="阻力位", color="#ec0000"))

    # 创建结果对象
    result_stock = StockScanResult(
        code="sh.000001",
        name="测试股票",
        industry="测试行业",
        selection_reasons={60: "60天窗口期内价格波动小于50%，均线高度粘合，波动率低，成交量稳定"},
        kline_data=kline_data,
        mark_lines=mark_lines
    )

    return [result_stock]

# 注意：我们已经有了根端点 (/), 不需要额外的 /api 端点
