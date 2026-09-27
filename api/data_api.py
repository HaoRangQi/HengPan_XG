"""
Data source catalog and preview API.

Read-only: reports which Baostock datasets are available, what each field
means, and returns a capped preview of rows. Nothing is stored locally.
"""
import re
import socket
import threading
import time
from datetime import datetime, timedelta
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Any, Callable, Dict, List, Optional, Tuple

import baostock as bs
import baostock.common.contants as bs_cons
from fastapi import APIRouter, HTTPException, Path, Query

router = APIRouter()

# Baostock keeps one module-global socket, so concurrent queries would
# interleave on the same connection. Serialize every access through this lock.
_bs_lock = threading.Lock()
_logged_in = False

# Full-market datasets hold ~9000 rows. Baostock pages the result set, so
# stopping early means we only pull the first page instead of all of them.
DEFAULT_PREVIEW_ROWS = 50
MAX_PREVIEW_ROWS = 500
# Upper bound when draining a time series to reach its newest rows.
TAIL_DRAIN_CAP = 10000

KLINE_FIELDS = "date,open,high,low,close,volume,turn,preclose,pctChg,peTTM,pbMRQ"

# Baostock codes look like "sh.600000" / "sz.000001". Checking the shape here
# turns a wasted round trip (which also costs a needless re-login, since a
# rejected query is indistinguishable from a dead session) into a plain 400.
_CODE_RE = re.compile(r"^(sh|sz|bj)\.\d{6}$")

# Catalog of every dataset this project can read, with the meaning of each
# field and which analyzer consumes it. Field names verified against the live
# API on 2026-09-24.
DATASETS: List[Dict[str, Any]] = [
    {
        "key": "stock_basic",
        "name": "股票列表",
        "api": "query_stock_basic",
        "summary": "全市场证券的代码、名称、上市日期与状态",
        "scale": "约 8981 条（全市场）",
        "params": ["code（可选，留空取全市场）"],
        "used_by": "扫描前置：prepare_stock_list 用它构建待扫股票池",
        "fields": [
            ["code", "证券代码，如 sh.600000"],
            ["code_name", "证券名称"],
            ["ipoDate", "上市日期"],
            ["outDate", "退市日期（在市为空）"],
            ["type", "证券类型：1 股票 / 2 指数 / 3 其它 / 4 可转债 / 5 ETF"],
            ["status", "上市状态：1 上市 / 0 退市"],
        ],
    },
    {
        "key": "stock_industry",
        "name": "行业分类",
        "api": "query_stock_industry",
        "summary": "证监会行业分类，用于行业多样性过滤",
        "scale": "约 5555 条（全市场）",
        "params": ["code（可选，留空取全市场）"],
        "used_by": "industry_filter：保证选出的股票分散在不同行业",
        "fields": [
            ["updateDate", "分类更新日期"],
            ["code", "证券代码"],
            ["code_name", "证券名称"],
            ["industry", "所属行业，如 J66货币金融服务"],
            ["industryClassification", "行业分类标准"],
        ],
    },
    {
        "key": "kline",
        "name": "日线行情",
        "api": "query_history_k_data_plus",
        "summary": "前复权日线，平台期识别的核心数据",
        "scale": "每个交易日 1 条",
        "params": ["code（必填）", "start / end 日期"],
        "used_by": "全部价格类分析：箱体检测、均线粘合、波动率、成交量、低位、快速下跌、突破预测",
        "fields": [
            ["date", "交易日期"],
            ["open", "开盘价（前复权）"],
            ["high", "最高价"],
            ["low", "最低价"],
            ["close", "收盘价"],
            ["volume", "成交量（股）"],
            ["turn", "换手率（%）"],
            ["preclose", "前收盘价"],
            ["pctChg", "涨跌幅（%）"],
            ["peTTM", "滚动市盈率"],
            ["pbMRQ", "市净率（最近报告期）"],
        ],
    },
    {
        "key": "growth",
        "name": "财务·成长能力",
        "api": "query_growth_data",
        "summary": "年报同比增长率",
        "scale": "每年 1 条",
        "params": ["code（必填）", "year", "quarter"],
        "used_by": "fundamental_analyzer，仅在 use_fundamental_filter 开启时生效（默认关闭）",
        "fields": [
            ["code", "证券代码"],
            ["pubDate", "报告发布日期"],
            ["statDate", "统计截止日期"],
            ["YOYEquity", "净资产同比增长率"],
            ["YOYAsset", "总资产同比增长率"],
            ["YOYNI", "净利润同比增长率"],
            ["YOYEPSBasic", "基本每股收益同比增长率"],
            ["YOYPNI", "归属母公司净利润同比增长率"],
        ],
    },
    {
        "key": "profit",
        "name": "财务·盈利能力",
        "api": "query_profit_data",
        "summary": "年报盈利指标，含 ROE 与每股收益",
        "scale": "每年 1 条",
        "params": ["code（必填）", "year", "quarter"],
        "used_by": "fundamental_analyzer，仅在 use_fundamental_filter 开启时生效（默认关闭）",
        "fields": [
            ["code", "证券代码"],
            ["pubDate", "报告发布日期"],
            ["statDate", "统计截止日期"],
            ["roeAvg", "净资产收益率（平均）"],
            ["npMargin", "销售净利率"],
            ["gpMargin", "销售毛利率（银行等行业可能为空）"],
            ["netProfit", "净利润（元）"],
            ["epsTTM", "滚动每股收益"],
            ["MBRevenue", "主营营业收入（元）"],
            ["totalShare", "总股本"],
            ["liqaShare", "流通股本"],
        ],
    },
    {
        "key": "balance",
        "name": "财务·偿债能力",
        "api": "query_balance_data",
        "summary": "年报资产负债结构指标",
        "scale": "每年 1 条",
        "params": ["code（必填）", "year", "quarter"],
        "used_by": "fundamental_analyzer，仅在 use_fundamental_filter 开启时生效（默认关闭）",
        "fields": [
            ["code", "证券代码"],
            ["pubDate", "报告发布日期"],
            ["statDate", "统计截止日期"],
            ["currentRatio", "流动比率（银行等行业可能为空）"],
            ["quickRatio", "速动比率"],
            ["cashRatio", "现金比率"],
            ["YOYLiability", "总负债同比增长率"],
            ["liabilityToAsset", "资产负债率"],
            ["assetToEquity", "权益乘数"],
        ],
    },
]

_DATASETS_BY_KEY = {d["key"]: d for d in DATASETS}


def _client_version() -> str:
    """
    Installed baostock version. Prefer package metadata: the module's own
    __version__ reads "00.9.40", which looks like a typo to a reader.
    """
    try:
        return pkg_version("baostock")
    except PackageNotFoundError:
        return getattr(bs, "__version__", "unknown")


def _probe_server(timeout: float = 3.0) -> Dict[str, Any]:
    """
    TCP-probe the Baostock server. Cheap (tens of ms) and, unlike bs.login(),
    it cannot hang: baostock creates its socket without a timeout, so an
    unreachable server blocks until the OS gives up (~75s).
    """
    host = bs_cons.BAOSTOCK_SERVER_IP
    port = bs_cons.BAOSTOCK_SERVER_PORT
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return {
            "host": host,
            "port": port,
            "reachable": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": None,
        }
    except OSError as exc:
        return {
            "host": host,
            "port": port,
            "reachable": False,
            "latency_ms": None,
            "error": str(exc),
        }


def _collect(rs, limit: int, tail: bool) -> Tuple[List[str], List[List[str]], bool]:
    """
    Drain a result set.

    Baostock returns rows oldest-first. For a time series the interesting end
    is the newest, so `tail` drains fully and keeps the last `limit` rows;
    otherwise we stop early, which for full-market lists avoids pulling every
    page (~9000 rows / 22s).
    """
    fields = list(rs.fields)
    rows: List[List[str]] = []
    truncated = False

    if tail:
        while rs.error_code == '0' and rs.next():
            rows.append(rs.get_row_data())
            if len(rows) > TAIL_DRAIN_CAP:
                # Absurd date range; keep memory bounded.
                rows = rows[-limit:]
                truncated = True
                break
        if len(rows) > limit:
            rows = rows[-limit:]
            truncated = True
        return fields, rows, truncated

    while rs.error_code == '0' and rs.next():
        if len(rows) >= limit:
            truncated = True
            break
        rows.append(rs.get_row_data())
    return fields, rows, truncated


def _run_query(make_rs: Callable[[], Any], limit: int, tail: bool = False) -> Dict[str, Any]:
    """
    Log in if needed and run one query, holding the global lock throughout.

    A scan task exiting BaostockConnectionManager calls bs.logout() on the
    shared socket, which invalidates our session; on failure we re-login once.
    """
    global _logged_in

    probe = _probe_server()
    if not probe["reachable"]:
        raise HTTPException(
            status_code=503,
            detail=f"Baostock 服务器不可达 ({probe['host']}:{probe['port']}): {probe['error']}",
        )

    with _bs_lock:
        last_error = ""
        for attempt in (1, 2):
            if not _logged_in:
                login_result = bs.login()
                if login_result.error_code != '0':
                    raise HTTPException(
                        status_code=503,
                        detail=f"Baostock 登录失败: {login_result.error_msg}",
                    )
                _logged_in = True

            started = time.perf_counter()
            rs = make_rs()
            if rs.error_code == '0':
                fields, rows, truncated = _collect(rs, limit, tail)
                return {
                    "fields": fields,
                    "rows": rows,
                    "row_count": len(rows),
                    "truncated": truncated,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                }

            last_error = rs.error_msg or f"error_code={rs.error_code}"
            # Session is probably dead; drop it so attempt 2 logs in again.
            _logged_in = False

        raise HTTPException(status_code=502, detail=f"Baostock 查询失败: {last_error}")


@router.get("/data/sources", summary="数据源与数据集目录",
            description="返回 Baostock 连通状态与可用数据集列表，不登录数据源，立即返回。")
def list_sources() -> Dict[str, Any]:
    """
    Data source status and dataset catalog. Does not log in, so it returns
    immediately.
    """
    return {
        "source": {
            "name": "Baostock",
            "client_version": _client_version(),
            "server": _probe_server(),
            "storage": "无本地存储，每次查询实时拉取",
        },
        "datasets": [
            {k: v for k, v in d.items() if k != "fields"} | {"field_count": len(d["fields"])}
            for d in DATASETS
        ],
    }


@router.get("/data/sources/{dataset_key}", summary="数据集字段说明",
            description="返回单个数据集的全部字段及含义。", responses={404: {"description": "未知数据集"}})
def describe_source(dataset_key: str = Path(description="数据集 key，见数据集目录")) -> Dict[str, Any]:
    """Full field list for one dataset."""
    dataset = _DATASETS_BY_KEY.get(dataset_key)
    if not dataset:
        raise HTTPException(status_code=404, detail=f"未知数据集: {dataset_key}")
    return dataset


@router.get("/data/preview", summary="预览原始数据",
            description="按证券代码实时查询某个数据集的若干条原始记录，只读，不落地存储。",
            responses={400: {"description": "参数不合法"}, 404: {"description": "未知数据集"},
                       502: {"description": "Baostock 查询失败"}, 503: {"description": "Baostock 不可达或登录失败"}})
def preview_dataset(
    dataset: str = Query(..., description="数据集 key，见 /api/data/sources"),
    code: str = Query("", description="证券代码，如 sh.600000"),
    start: Optional[str] = Query(None, description="日线起始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="日线结束日期 YYYY-MM-DD"),
    year: Optional[int] = Query(None, description="财务数据年份"),
    quarter: int = Query(4, ge=1, le=4, description="财务数据季度"),
    limit: int = Query(DEFAULT_PREVIEW_ROWS, ge=1, le=MAX_PREVIEW_ROWS, description="返回条数"),
) -> Dict[str, Any]:
    """
    Preview rows from one dataset.

    Declared sync (not async) on purpose: Baostock calls block, and an async
    endpoint would stall the whole event loop. FastAPI runs this in a
    threadpool instead.
    """
    spec = _DATASETS_BY_KEY.get(dataset)
    if not spec:
        raise HTTPException(status_code=404, detail=f"未知数据集: {dataset}")

    code = code.strip()
    if code and not _CODE_RE.match(code):
        raise HTTPException(
            status_code=400,
            detail=f"证券代码格式不正确: {code}。应为 sh./sz./bj. 加 6 位数字，如 sh.600000",
        )

    params: Dict[str, Any] = {}
    # Time series: show the newest rows, not the oldest.
    tail = dataset == "kline"

    if dataset == "stock_basic":
        params = {"code": code}
        make_rs = lambda: bs.query_stock_basic(code=code)
    elif dataset == "stock_industry":
        params = {"code": code}
        make_rs = lambda: bs.query_stock_industry(code=code)
    elif dataset == "kline":
        if not code:
            raise HTTPException(status_code=400, detail="日线行情需要指定证券代码")
        end = end or datetime.now().strftime('%Y-%m-%d')
        start = start or (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        params = {"code": code, "start": start, "end": end, "adjustflag": "2（前复权）"}
        make_rs = lambda: bs.query_history_k_data_plus(
            code, KLINE_FIELDS,
            start_date=start, end_date=end, frequency="d", adjustflag="2",
        )
    elif dataset in ("growth", "profit", "balance"):
        if not code:
            raise HTTPException(status_code=400, detail=f"{spec['name']} 需要指定证券代码")
        # Only last year's annual report is reliably published.
        year = year or datetime.now().year - 1
        params = {"code": code, "year": year, "quarter": quarter}
        query_fn = getattr(bs, f"query_{dataset}_data")
        make_rs = lambda: query_fn(code=code, year=year, quarter=quarter)
    else:  # pragma: no cover - guarded by the lookup above
        raise HTTPException(status_code=404, detail=f"未知数据集: {dataset}")

    result = _run_query(make_rs, limit, tail=tail)
    return {
        "dataset": dataset,
        "name": spec["name"],
        "api": spec["api"],
        "params": params,
        "field_labels": dict(spec["fields"]),
        "truncated_note": (
            "仅显示最近的记录，更早的已省略" if tail else "仅显示前若干条，后续记录已省略"
        ),
        **result,
    }
