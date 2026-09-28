"""加密-U 本地平台扫描接口。"""
from __future__ import annotations

import traceback
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query
from pydantic import BaseModel, Field

from ..task_manager import TaskStatus, task_manager
from . import db
from .platform_history import delete, get, list_all, save
from .platform_scan import (CATEGORY_LABELS, analyze_crypto_platform,
                             build_crypto_frame, category_defaults, crypto_kline_records,
                             normalize_crypto_symbols)
from .reader import load_kline

router = APIRouter()
_extras: Dict[str, Dict] = {}


class CryptoCategoryParams(BaseModel):
    box_threshold: Optional[float] = Field(None, gt=0, le=1)
    ma_diff_threshold: Optional[float] = Field(None, gt=0, le=1)
    volatility_threshold: Optional[float] = Field(None, gt=0, le=1)


class CryptoPlatformScanRequest(BaseModel):
    categories: List[str] = Field(default_factory=lambda: list(db.CATEGORIES), min_length=1)
    symbols: Optional[List[str]] = Field(None, max_length=1000)
    windows: List[int] = Field(default_factory=lambda: [40, 80, 120], min_length=1, max_length=5)
    category_params: Dict[str, CryptoCategoryParams] = Field(default_factory=dict)
    use_volume_analysis: bool = False
    use_box_detection: bool = True
    box_quality_threshold: float = Field(0.6, ge=0, le=1)
    limit_count: Optional[int] = Field(None, ge=1, le=5000)


def _validate_request(request: CryptoPlatformScanRequest):
    unknown = set(request.categories) - set(db.CATEGORIES)
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知加密类别：{', '.join(sorted(unknown))}")
    if any(window < 10 or window > 1500 for window in request.windows):
        raise HTTPException(status_code=422, detail="窗口期应在 10 到 1500 根 K 线之间")
    if len(set(request.windows)) != len(request.windows):
        raise HTTPException(status_code=422, detail="窗口期不能重复")
    unknown_params = set(request.category_params) - set(db.CATEGORIES)
    if unknown_params:
        raise HTTPException(status_code=422, detail="存在未知加密类别参数")


def _params_for(category: str, request: CryptoPlatformScanRequest):
    defaults = category_defaults(category)
    override = request.category_params.get(category)
    if override:
        for key, value in override.model_dump(exclude_none=True).items():
            defaults[key] = value
    return defaults


def _run_scan(task_id: str, request: Dict):
    task = task_manager.get_task(task_id)
    try:
        with db.open_db() as conn:
            inventory = db.symbol_pool(conn, request["categories"], symbols=request.get("symbols"))
            symbols = normalize_crypto_symbols(inventory, request["categories"], request.get("symbols"))
            if not symbols:
                raise ValueError("所选类别没有本地交易对，请先到「数据管理」同步加密行情")
            task_manager.update_task(task_id, status=TaskStatus.RUNNING, total=len(symbols),
                                     message=f"已准备 {len(symbols)} 个交易对，开始读取本地 60 分钟行情…")
            scan_request = CryptoPlatformScanRequest(**request)
            results = []
            for index, symbol_info in enumerate(symbols, start=1):
                if task_manager.is_cancel_requested(task_id):
                    break
                frame = build_crypto_frame(
                    load_kline(conn, "1h", [symbol_info["category"]], [symbol_info["symbol"]]))
                if len(frame) < max(request["windows"]):
                    task_manager.update_task(task_id, scanned=index, message=f"正在分析 {index}/{len(symbols)}：{symbol_info['symbol']}（数据不足）")
                    continue
                params = _params_for(symbol_info["category"], scan_request)
                analysis = analyze_crypto_platform(
                    frame, request["windows"], **params,
                    use_volume_analysis=request["use_volume_analysis"],
                    use_box_detection=request["use_box_detection"],
                    box_quality_threshold=request["box_quality_threshold"],
                )
                if analysis["is_platform"]:
                    result = {
                        "code": symbol_info["symbol"], "name": symbol_info.get("baseAsset") or symbol_info["symbol"],
                        "category": symbol_info["category"], "category_label": CATEGORY_LABELS[symbol_info["category"]],
                        "quote_volume": symbol_info.get("quoteVolume", 0),
                        "last_price": symbol_info.get("lastPrice"),
                        "platform_windows": analysis["platform_windows"],
                        "selection_reasons": analysis["selection_reasons"],
                        "details": analysis["details"], "mark_lines": analysis.get("mark_lines", []),
                        "kline_data": crypto_kline_records(frame),
                    }
                    if not request.get("limit_count") or len(results) < request["limit_count"]:
                        results.append(result)
                        task_manager.append_streamed(task_id, [result])
                task_manager.update_task(task_id, scanned=index, found=len(results),
                                         progress=int(index / len(symbols) * 100),
                                         message=f"已分析 {index}/{len(symbols)} 个交易对，发现 {len(results)} 个平台期")
            cancelled = task_manager.is_cancel_requested(task_id)
            task_manager.update_task(task_id, status=TaskStatus.CANCELLED if cancelled else TaskStatus.COMPLETED,
                                     progress=100, result=results,
                                     message=f"{'已停止' if cancelled else '扫描完成'}：返回 {len(results)} 个交易对")
            done = task_manager.get_task(task_id)
            save(task_id, {"task_id": task_id, "status": done.status.value, "message": done.message,
                           "created_at": done.created_at, "completed_at": done.completed_at,
                           "categories": request["categories"], "windows": request["windows"],
                           "request": request, "scanned": done.scanned, "total": done.total,
                           "results": results})
    except Exception as error:
        task_manager.update_task(task_id, status=TaskStatus.FAILED,
                                 message=f"加密平台扫描失败：{error}", error=f"{error}\n{traceback.format_exc()}")


@router.post("/crypto/platform/scan/start")
async def start_crypto_platform_scan(request: CryptoPlatformScanRequest, background_tasks: BackgroundTasks):
    _validate_request(request)
    task_id = task_manager.create_task()
    payload = request.model_dump()
    _extras[task_id] = payload
    background_tasks.add_task(_run_scan, task_id, payload)
    return {"task_id": task_id, "message": "加密-U 扫描任务已创建，正在读取本地行情…"}


@router.get("/crypto/platform/scan/status/{task_id}")
async def crypto_platform_scan_status(task_id: str = Path(), since: int = Query(0, ge=0)):
    task = task_manager.get_task(task_id)
    if not task or task_id not in _extras:
        raise HTTPException(status_code=404, detail="扫描任务不存在")
    return {**task.to_dict(since=since), "params": _extras[task_id]}


@router.post("/crypto/platform/scan/cancel/{task_id}")
async def cancel_crypto_platform_scan(task_id: str):
    if not task_manager.request_cancel(task_id):
        raise HTTPException(status_code=404, detail="扫描任务不存在或已结束")
    return {"success": True, "message": "已请求停止扫描"}


@router.get("/crypto/platform/scan/history")
async def crypto_platform_history_list():
    return {"histories": list_all()}


@router.get("/crypto/platform/scan/history/{history_id}")
async def crypto_platform_history_detail(history_id: str):
    snapshot = get(history_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="历史记录不存在")
    return snapshot


@router.delete("/crypto/platform/scan/history/{history_id}")
async def delete_crypto_platform_history(history_id: str):
    if not delete(history_id):
        raise HTTPException(status_code=404, detail="历史记录不存在")
    return {"history_id": history_id, "deleted": True}
