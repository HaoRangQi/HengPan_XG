"""本地行情仓库 API：概览、同步、查询和清理。"""
import os
import threading
import traceback
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from ..task_manager import TaskStatus, task_manager
from . import db, sync
from .reader import load_kline_60m

router = APIRouter()
_sync_guard = threading.Lock()
_active_sync_task_id = None


class StoreSyncRequest(BaseModel):
    boards: List[str] = Field(default_factory=lambda: list(db.DEFAULT_BOARDS))
    frequency: str = Field("60", pattern=r"^60$")
    force_metadata: bool = False
    workers: int = Field(sync.SYNC_WORKERS, ge=1, le=10)
    # 留空表示按本地进度增量同步；指定 start 则补该区间的历史
    start: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    codes: Optional[List[str]] = Field(None, max_length=500)


class CleanupRequest(BaseModel):
    boards: List[str] = Field(default_factory=lambda: list(db.KLINE_BOARDS))
    keep_days: int = Field(sync.RETENTION_DAYS, ge=1, le=3650)
    apply: bool = False


class RefetchRequest(BaseModel):
    code: str = Field(pattern=r"^(sh|sz)\.\d{6}$")
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


def _check_boards(boards):
    unknown = set(boards) - set(db.KLINE_BOARDS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知板块：{', '.join(sorted(unknown))}")
    if not boards:
        raise HTTPException(status_code=422, detail="至少选择一个板块")
    return list(dict.fromkeys(boards))


def _active_sync():
    global _active_sync_task_id
    with _sync_guard:
        task = task_manager.get_task(_active_sync_task_id) if _active_sync_task_id else None
        if task and task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return task
        _active_sync_task_id = None
        return None


def _ensure_store_idle():
    task = _active_sync()
    if task:
        raise HTTPException(
            status_code=409,
            detail=f"本地行情正在同步（任务 {task.task_id}），请先等待完成或停止任务",
        )


@router.get("/store/overview", summary="本地数据概览")
def store_overview():
    active = _active_sync()
    with db.open_db() as conn:
        boards = []
        for board in db.KLINE_BOARDS:
            item = db.board_stats(conn, "60", board)
            item["pool_codes"] = conn.execute(
                "SELECT COUNT(*) FROM stock_basic WHERE board=? AND status='1'", (board,)).fetchone()[0]
            boards.append(item)
        return {
            "database": {"path": db.DB_PATH, "size": os.path.getsize(db.DB_PATH) if os.path.exists(db.DB_PATH) else 0},
            "boards": boards,
            "stock_count": conn.execute("SELECT COUNT(*) FROM stock_basic").fetchone()[0],
            "industry_count": conn.execute("SELECT COUNT(*) FROM stock_industry").fetchone()[0],
            "trade_days": len(db.trading_days(conn)),
            "retention_days": sync.RETENTION_DAYS,
            "active_sync": active.to_dict() if active else None,
            "logs": sync.recent_logs(conn, 10),
        }


def _run_sync_task(task_id, request):
    global _active_sync_task_id
    try:
        task_manager.update_task(task_id, status=TaskStatus.RUNNING, message="正在同步本地行情…")
        with db.open_db() as conn:
            def progress(done, total, rows, message):
                task_manager.update_task(task_id, progress=(int(done / total * 100) if total else 5),
                                         scanned=done, total=total, found=rows, message=message)

            result = sync.sync_all(conn, boards=request["boards"], frequency=request["frequency"],
                                   force_metadata=request["force_metadata"], workers=request["workers"],
                                   start=request.get("start"), end=request.get("end"),
                                   codes=request.get("codes"),
                                   update_progress=progress,
                                   should_cancel=lambda: task_manager.is_cancel_requested(task_id))
        status = TaskStatus.CANCELLED if result.get("cancelled") else TaskStatus.COMPLETED
        summary = (f"请求 {result.get('requests', 0)} 次，写入 {result.get('rows', 0)} 根，"
                   f"{result.get('up_to_date', 0)} 只已是最新未请求")
        task_manager.update_task(task_id, status=status, progress=100, result=result,
                                 message=f"同步已停止：{summary}" if result.get("cancelled")
                                 else f"同步完成：{summary}")
    except Exception as error:
        task_manager.update_task(task_id, status=TaskStatus.FAILED,
                                 message="同步失败", error=f"{error}\n{traceback.format_exc()}")
    finally:
        with _sync_guard:
            if _active_sync_task_id == task_id:
                _active_sync_task_id = None


@router.post("/store/sync", summary="启动本地数据同步")
async def start_store_sync(request: StoreSyncRequest, background_tasks: BackgroundTasks):
    global _active_sync_task_id
    request.boards = _check_boards(request.boards)
    if request.start and request.end and request.start > request.end:
        raise HTTPException(status_code=422, detail="起始日期不能晚于结束日期")
    if request.codes:
        unknown = [c for c in request.codes if db.board_of(c) not in db.KLINE_BOARDS]
        if unknown:
            raise HTTPException(status_code=422,
                                detail=f"不支持的证券代码：{', '.join(unknown[:5])}")
    with _sync_guard:
        active = task_manager.get_task(_active_sync_task_id) if _active_sync_task_id else None
        if active and active.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            raise HTTPException(
                status_code=409,
                detail=f"已有本地同步任务正在运行：{active.task_id}",
            )
        task_id = task_manager.create_task()
        _active_sync_task_id = task_id
    background_tasks.add_task(_run_sync_task, task_id, request.model_dump())
    return {"task_id": task_id, "message": "本地数据同步任务已创建"}


@router.get("/store/sync/status/{task_id}", summary="查询本地同步进度")
async def get_store_sync_status(task_id: str, since: int = Query(0, ge=0)):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="同步任务不存在")
    return task.to_dict(since=since)


@router.post("/store/sync/cancel/{task_id}", summary="取消本地数据同步")
async def cancel_store_sync(task_id: str):
    if not task_manager.request_cancel(task_id):
        raise HTTPException(status_code=404, detail="同步任务不存在或已结束")
    return {"success": True, "message": "已请求停止同步"}


@router.get("/store/stocks", summary="板块股票清单（含本地行情统计）")
def list_store_stocks(
    boards: List[str] = Query(default_factory=lambda: list(db.DEFAULT_BOARDS)),
    keyword: Optional[str] = Query(None, max_length=32),
    having: str = Query("all", pattern=r"^(all|with|without)$"),
    include_delisted: bool = Query(False),
):
    """一次返回整个板块的股票（约 1700 只，50 毫秒），前端拿去本地搜索和筛选。"""
    boards = _check_boards(boards)
    with db.open_readonly_db() as conn:
        stocks = db.stock_inventory(conn, boards, keyword=keyword, having=having,
                                    include_delisted=include_delisted)
    return {
        "boards": boards,
        "total": len(stocks),
        "with_kline": sum(1 for stock in stocks if stock["bars"]),
        "stocks": stocks,
    }


@router.get("/store/kline", summary="查询本地 60 分钟线")
def get_store_kline(
    code: str = Query(..., pattern=r"^(sh|sz)\.\d{6}$"),
    start: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    adjust: str = Query("qfq", pattern=r"^(qfq|hfq|raw)$"),
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    board = db.board_of(code)
    if board not in db.KLINE_BOARDS:
        raise HTTPException(status_code=422, detail=f"不支持的证券代码：{code}")
    with db.open_readonly_db() as conn:
        frame = load_kline_60m(conn, [board], start=start, end=end,
                                adjust=adjust, codes=[code])
    total = len(frame)
    page = frame.iloc[offset:offset + limit].astype(object)
    rows = page.where(page.notna(), None).to_dict(orient="records")
    return {"code": code, "adjust": adjust, "total": total, "offset": offset,
            "limit": limit, "row_count": len(rows), "rows": rows}


@router.delete("/store/kline", summary="删除指定本地 60 分钟线")
def delete_store_kline(
    code: str = Query(..., pattern=r"^(sh|sz)\.\d{6}$"),
    start: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    _ensure_store_idle()
    board = db.board_of(code)
    if board not in db.KLINE_BOARDS:
        raise HTTPException(status_code=422, detail=f"不支持的证券代码：{code}")
    where, params = ["code = ?"], [code]
    if start:
        where.append("date >= ?")
        params.append(start)
    if end:
        where.append("date <= ?")
        params.append(end)
    with db.open_db() as conn:
        cursor = conn.execute(
            f"DELETE FROM {db.kline_table('60', board)} WHERE " + " AND ".join(where), params)
        conn.commit()
        log_id = sync.start_log(conn, "delete", [board])
        sync.finish_log(conn, log_id, "completed", {
            "rows": cursor.rowcount,
            "message": f"{code} {start or '最早'} 至 {end or '最新'}",
        })
    return {"code": code, "deleted": cursor.rowcount}


@router.delete("/store/board/{board}", summary="清空指定板块的本地 60 分钟线")
def clear_store_board(board: str):
    _ensure_store_idle()
    if board not in db.KLINE_BOARDS:
        raise HTTPException(status_code=422, detail=f"未知板块：{board}")
    with db.open_db() as conn:
        cursor = conn.execute(f"DELETE FROM {db.kline_table('60', board)}")
        conn.commit()
        log_id = sync.start_log(conn, "clear", [board])
        sync.finish_log(conn, log_id, "completed", {"rows": cursor.rowcount})
    return {"board": board, "deleted": cursor.rowcount}


@router.post("/store/refetch", summary="重新拉取单只股票并覆盖本地数据")
def refetch_store_kline(request: RefetchRequest):
    _ensure_store_idle()
    board = db.board_of(request.code)
    if board not in db.KLINE_BOARDS:
        raise HTTPException(status_code=422, detail=f"不支持的证券代码：{request.code}")
    if request.start > request.end:
        raise HTTPException(status_code=422, detail="起始日期不能晚于结束日期")
    from ..data_fetcher import BaostockConnectionManager
    with BaostockConnectionManager():
        rows = sync.fetch_kline_rows(request.code, request.start, request.end, "60")
    if not rows:
        raise HTTPException(status_code=502, detail="数据源没有返回任何 K 线，本地原数据未修改")
    with db.open_db() as conn:
        conn.execute(
            f"DELETE FROM {db.kline_table('60', board)} WHERE code=? AND date>=? AND date<=?",
            (request.code, request.start, request.end),
        )
        written = db.upsert(conn, db.kline_table("60", board), db.MINUTE_COLUMNS, rows)
        conn.commit()
        log_id = sync.start_log(conn, "refetch", [board])
        sync.finish_log(conn, log_id, "completed", {"requests": 1, "rows": written, "failed": 0})
    return {"code": request.code, "rows": written, "start": request.start, "end": request.end}


@router.post("/store/cleanup", summary="清理过期本地行情")
def cleanup_store(request: CleanupRequest):
    _ensure_store_idle()
    request.boards = _check_boards(request.boards)
    with db.open_db() as conn:
        return sync.cleanup(conn, keep_days=request.keep_days, boards=request.boards,
                            dry_run=not request.apply)


@router.post("/store/vacuum", summary="压缩本地数据库")
def vacuum_store():
    _ensure_store_idle()
    with db.open_db() as conn:
        log_id = sync.start_log(conn, "vacuum", [])
        result = sync.vacuum(conn)
        sync.finish_log(conn, log_id, "completed", {
            "message": f"释放 {result['freed']} 字节",
        })
        return result


@router.get("/store/log", summary="查看本地同步日志")
def get_store_logs(limit: int = Query(20, ge=1, le=200)):
    with db.open_db() as conn:
        return {"logs": sync.recent_logs(conn, limit)}
