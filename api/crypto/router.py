"""加密货币本地行情 API：概览、连通性、币池清单、K 线查询、同步和维护。前缀 /api/crypto，与 A 股完全分开。"""
import os
import threading
import traceback
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from ..task_manager import TaskStatus, task_manager
from . import db, sync
from .binance import BinanceBanned, BinanceClient, BinanceError, BinanceRestricted
from .reader import load_kline

router = APIRouter()
_sync_guard = threading.Lock()
_active_sync_task_id = None

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class CryptoSyncRequest(BaseModel):
    categories: List[str] = Field(default_factory=lambda: list(db.CATEGORIES),
                                  description="perpetual 加密永续 / tradifi TradFi 永续")
    interval: str = Field("1h", pattern=r"^1h$")
    # 留空表示按本地进度增量同步；指定 start 则补该区间（北京日期）
    start: Optional[str] = Field(None, pattern=DATE_PATTERN)
    end: Optional[str] = Field(None, pattern=DATE_PATTERN)
    symbols: Optional[List[str]] = Field(None, max_length=1000)
    min_quote_volume: float = Field(0, ge=0, description="24 小时成交额下限（USDT），0 表示不过滤")
    force_metadata: bool = False
    workers: int = Field(sync.SYNC_WORKERS, ge=1, le=16)


class CryptoCleanupRequest(BaseModel):
    categories: List[str] = Field(default_factory=lambda: list(db.CATEGORIES))
    keep_days: int = Field(sync.RETENTION_DAYS, ge=1, le=3650)
    apply: bool = False


class CryptoRefetchRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=40)
    start: str = Field(pattern=DATE_PATTERN)
    end: str = Field(pattern=DATE_PATTERN)


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------

def _check_categories(categories):
    unknown = set(categories) - set(db.CATEGORIES)
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知类别：{', '.join(sorted(unknown))}")
    if not categories:
        raise HTTPException(status_code=422, detail="至少选择一个类别")
    return list(dict.fromkeys(categories))


def _source_error(error):
    """把 Binance 的整轮性错误转成对用户友好的 HTTP 错误。"""
    if isinstance(error, (BinanceRestricted, BinanceBanned)):
        return HTTPException(status_code=503, detail=str(error))
    return HTTPException(status_code=502, detail=str(error))


def _category_for(conn, symbol):
    """交易对所在类别：先查币池，查不到（例如已下架）再看哪张 K 线表里有它。"""
    category = db.category_of(conn, symbol)
    if category:
        return category
    for candidate in db.CATEGORIES:
        hit = conn.execute(f'SELECT 1 FROM {db.kline_table("1h", candidate)} WHERE "symbol"=? LIMIT 1',
                           (symbol,)).fetchone()
        if hit:
            return candidate
    raise HTTPException(status_code=404, detail=f"本地没有交易对 {symbol}，请先同步币池")


def _date_range_ms(start, end):
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="起始日期不能晚于结束日期")
    return (sync.beijing_day_start_ms(start) if start else None,
            sync.beijing_day_end_ms(end) if end else None)


def _active_sync():
    global _active_sync_task_id
    with _sync_guard:
        task = task_manager.get_task(_active_sync_task_id) if _active_sync_task_id else None
        if task and task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return task
        _active_sync_task_id = None
        return None


def _ensure_idle():
    task = _active_sync()
    if task:
        raise HTTPException(status_code=409,
                            detail=f"加密行情正在同步（任务 {task.task_id}），请先等待完成或停止任务")


# --------------------------------------------------------------------------
# 查询
# --------------------------------------------------------------------------

@router.get("/crypto/overview", summary="加密行情库概览")
def crypto_overview():
    active = _active_sync()
    with db.open_db() as conn:
        categories = [db.category_stats(conn, "1h", c) for c in db.CATEGORIES]
        for item in categories:
            item["first_time"] = sync.format_beijing(item["first_time"])
            item["last_time"] = sync.format_beijing(item["last_time"])
        ticker_at = conn.execute("SELECT MAX(updated_at) FROM crypto_ticker_24hr").fetchone()[0]
        return {
            "database": {"path": db.DB_PATH,
                         "size": os.path.getsize(db.DB_PATH) if os.path.exists(db.DB_PATH) else 0},
            "interval": "1h",
            "categories": categories,
            "symbol_count": sum(item["pool_symbols"] for item in categories),
            "symbols_synced_at": db.get_meta(conn, "symbols_synced_at"),
            "ticker_updated_at": ticker_at,
            "retention_days": sync.RETENTION_DAYS,
            "active_sync": active.to_dict() if active else None,
            "logs": sync.recent_logs(conn, 10),
        }


@router.get("/crypto/ping", summary="检测能否访问 Binance")
def crypto_ping():
    """区分三种情况：可访问 / 出口在受限地区（451）/ 其他网络故障，页面据此给出提示。"""
    client = BinanceClient()
    try:
        client.ping()
        return {"ok": True, "status": "ok", "message": "Binance 可以访问",
                "used_weight": client.used_weight}
    except BinanceRestricted as error:
        return {"ok": False, "status": "restricted", "message": str(error)}
    except BinanceBanned as error:
        return {"ok": False, "status": "banned", "message": str(error)}
    except BinanceError as error:
        return {"ok": False, "status": "error", "message": str(error)}


@router.get("/crypto/symbols", summary="交易对清单（含本地 K 线统计）")
def list_crypto_symbols(
    categories: List[str] = Query(default_factory=lambda: list(db.CATEGORIES)),
    having: str = Query("all", pattern=r"^(all|with|without)$"),
    include_inactive: bool = Query(False, description="是否包含下架结算中等非交易状态"),
):
    categories = _check_categories(categories)
    with db.open_db() as conn:
        symbols = db.symbol_inventory(conn, categories, having=having,
                                      include_inactive=include_inactive)
    for item in symbols:
        item["first_time"] = sync.format_beijing(item["first_time"])
        item["last_time"] = sync.format_beijing(item["last_time"])
        item["onboardDate"] = sync.format_beijing(item["onboardDate"])
    return {"categories": categories, "total": len(symbols),
            "with_kline": sum(1 for item in symbols if item["bars"]), "symbols": symbols}


@router.get("/crypto/kline", summary="查询本地 1 小时线")
def get_crypto_kline(
    symbol: str = Query(..., min_length=2, max_length=40),
    start: Optional[str] = Query(None, pattern=DATE_PATTERN, description="北京日期"),
    end: Optional[str] = Query(None, pattern=DATE_PATTERN, description="北京日期"),
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    start_ms, end_ms = _date_range_ms(start, end)
    with db.open_db() as conn:
        category = _category_for(conn, symbol)
        frame = load_kline(conn, "1h", [category], [symbol], start_ms, end_ms)
    total = len(frame)
    page = frame.iloc[offset:offset + limit].drop(columns=["category", "ignore"], errors="ignore")
    page = page.astype(object).where(page.notna(), None)
    return {"symbol": symbol, "category": category, "total": total, "offset": offset,
            "limit": limit, "row_count": len(page), "rows": page.to_dict(orient="records")}


# --------------------------------------------------------------------------
# 同步
# --------------------------------------------------------------------------

def _run_sync_task(task_id, request):
    global _active_sync_task_id
    try:
        task_manager.update_task(task_id, status=TaskStatus.RUNNING, message="正在同步加密行情…")
        with db.open_db() as conn:
            def progress(done, total, rows, message):
                task_manager.update_task(task_id, progress=(int(done / total * 100) if total else 5),
                                         scanned=done, total=total, found=rows, message=message)

            result = sync.sync_all(
                conn, categories=request["categories"], interval=request["interval"],
                start=request.get("start"), end=request.get("end"), symbols=request.get("symbols"),
                min_quote_volume=request["min_quote_volume"],
                force_metadata=request["force_metadata"], workers=request["workers"],
                update_progress=progress,
                should_cancel=lambda: task_manager.is_cancel_requested(task_id))
        status = TaskStatus.CANCELLED if result.get("cancelled") else TaskStatus.COMPLETED
        summary = (f"请求 {result.get('requests', 0)} 次，写入 {result.get('rows', 0)} 根，"
                   f"{result.get('up_to_date', 0)} 个已是最新未请求")
        task_manager.update_task(task_id, status=status, progress=100, result=result,
                                 message=f"同步已停止：{summary}" if result.get("cancelled")
                                 else f"同步完成：{summary}")
    except Exception as error:
        detail = str(error) if isinstance(error, (BinanceError, ValueError)) else \
            f"{error}\n{traceback.format_exc()}"
        task_manager.update_task(task_id, status=TaskStatus.FAILED, message=str(error), error=detail)
    finally:
        with _sync_guard:
            if _active_sync_task_id == task_id:
                _active_sync_task_id = None


@router.post("/crypto/sync", summary="启动加密行情同步")
async def start_crypto_sync(request: CryptoSyncRequest, background_tasks: BackgroundTasks):
    global _active_sync_task_id
    request.categories = _check_categories(request.categories)
    if request.start and request.end and request.start > request.end:
        raise HTTPException(status_code=422, detail="起始日期不能晚于结束日期")
    with _sync_guard:
        active = task_manager.get_task(_active_sync_task_id) if _active_sync_task_id else None
        if active and active.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            raise HTTPException(status_code=409, detail=f"已有加密同步任务正在运行：{active.task_id}")
        task_id = task_manager.create_task()
        _active_sync_task_id = task_id
    background_tasks.add_task(_run_sync_task, task_id, request.model_dump())
    return {"task_id": task_id, "message": "加密行情同步任务已创建"}


@router.get("/crypto/sync/status/{task_id}", summary="查询加密同步进度")
async def get_crypto_sync_status(task_id: str, since: int = Query(0, ge=0)):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="同步任务不存在")
    return task.to_dict(since=since)


@router.post("/crypto/sync/cancel/{task_id}", summary="取消加密同步")
async def cancel_crypto_sync(task_id: str):
    if not task_manager.request_cancel(task_id):
        raise HTTPException(status_code=404, detail="同步任务不存在或已结束")
    return {"success": True, "message": "已请求停止同步"}


# --------------------------------------------------------------------------
# 删改与维护
# --------------------------------------------------------------------------

@router.delete("/crypto/kline", summary="删除指定交易对的本地 K 线")
def delete_crypto_kline(
    symbol: str = Query(..., min_length=2, max_length=40),
    start: Optional[str] = Query(None, pattern=DATE_PATTERN),
    end: Optional[str] = Query(None, pattern=DATE_PATTERN),
):
    _ensure_idle()
    start_ms, end_ms = _date_range_ms(start, end)
    with db.open_db() as conn:
        category = _category_for(conn, symbol)
        where, params = ['"symbol" = ?'], [symbol]
        if start_ms is not None:
            where.append('"open_time" >= ?')
            params.append(start_ms)
        if end_ms is not None:
            where.append('"open_time" <= ?')
            params.append(end_ms)
        cursor = conn.execute(f"DELETE FROM {db.kline_table('1h', category)} WHERE "
                              + " AND ".join(where), params)
        conn.commit()
        log_id = sync.start_log(conn, "delete", [category])
        sync.finish_log(conn, log_id, "completed", {
            "rows": cursor.rowcount, "message": f"{symbol} {start or '最早'} 至 {end or '最新'}"})
    return {"symbol": symbol, "deleted": cursor.rowcount}


@router.delete("/crypto/category/{category}", summary="清空某一类别的本地 K 线")
def clear_crypto_category(category: str):
    _ensure_idle()
    _check_categories([category])
    with db.open_db() as conn:
        cursor = conn.execute(f"DELETE FROM {db.kline_table('1h', category)}")
        conn.commit()
        log_id = sync.start_log(conn, "clear", [category])
        sync.finish_log(conn, log_id, "completed", {"rows": cursor.rowcount})
    return {"category": category, "deleted": cursor.rowcount}


@router.post("/crypto/refetch", summary="重新拉取单个交易对并覆盖本地数据")
def refetch_crypto_kline(request: CryptoRefetchRequest):
    _ensure_idle()
    start_ms, end_ms = _date_range_ms(request.start, request.end)
    period = db.INTERVALS["1h"]
    begin = -(-start_ms // period) * period
    end_open = min(sync.last_closed_open(period), (end_ms // period) * period)
    if begin > end_open:
        raise HTTPException(status_code=422, detail="所选区间内没有已走完的 K 线")
    client = BinanceClient()
    with db.open_db() as conn:
        category = _category_for(conn, request.symbol)
        try:
            rows, requests = sync.fetch_symbol_klines(client, request.symbol, "1h", begin, end_open)
        except BinanceError as error:
            raise _source_error(error)
        if not rows:
            raise HTTPException(status_code=502, detail="数据源没有返回任何 K 线，本地原数据未修改")
        table = db.kline_table("1h", category)
        conn.execute(f'DELETE FROM {table} WHERE "symbol"=? AND "open_time">=? AND "open_time"<=?',
                     (request.symbol, begin, end_open))
        written = db.upsert(conn, table, db.KLINE_COLUMNS, rows)
        conn.commit()
        log_id = sync.start_log(conn, "refetch", [category])
        sync.finish_log(conn, log_id, "completed", {"requests": requests, "rows": written})
    return {"symbol": request.symbol, "rows": written, "requests": requests,
            "start": request.start, "end": request.end}


@router.post("/crypto/cleanup", summary="清理过期的加密行情")
def cleanup_crypto(request: CryptoCleanupRequest):
    _ensure_idle()
    categories = _check_categories(request.categories)
    with db.open_db() as conn:
        return sync.cleanup(conn, keep_days=request.keep_days, categories=categories,
                            dry_run=not request.apply)


@router.post("/crypto/vacuum", summary="压缩加密行情库")
def vacuum_crypto():
    _ensure_idle()
    with db.open_db() as conn:
        log_id = sync.start_log(conn, "vacuum", [])
        result = sync.vacuum(conn)
        sync.finish_log(conn, log_id, "completed", {"message": f"释放 {result['freed']} 字节"})
        return result


@router.get("/crypto/log", summary="查看加密同步日志")
def get_crypto_logs(limit: int = Query(20, ge=1, le=200)):
    with db.open_db() as conn:
        return {"logs": sync.recent_logs(conn, limit)}
