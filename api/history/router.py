"""
统一的扫描历史接口。四个页面的历史都从这里读写，老路径在各自模块里做薄封装。

列表和详情都不返回 K 线：列表只查 scan_run，详情带入选清单，看图时按
/history/{run_id}/kline/{code} 取一只票。
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from . import db, store
from .adapters import KIND_SPECS

router = APIRouter()


class HistoryUpdateRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=2000, description="手写备注，留空表示不改")
    pinned: Optional[bool] = Field(None, description="置顶保护：置顶的记录不会被清理删除")


class HistoryCleanupRequest(BaseModel):
    apply: bool = Field(False, description="默认只预览，确认后传 true 执行清理")
    keep_count: Optional[int] = Field(None, ge=1, le=10000, description="只保留最新的 N 条")
    keep_days: Optional[int] = Field(None, ge=1, le=3650, description="只保留最近 N 天")
    max_kline_bytes: Optional[int] = Field(None, ge=1, description="K 线总体积上限，超出的从旧到新删")
    kind: Optional[str] = Field(None, description="只清理某个页面的历史，留空清理全部")


@router.get("/history", tags=["扫描历史"], summary="扫描历史列表",
            description="按市场、页面、周期、状态、扫描日、标的筛选并分页。只返回元数据，不含结果和 K 线。")
def list_history(
        market: Optional[Literal["a", "crypto"]] = Query(None, description="a 股或 crypto；留空不限"),
        kind: Optional[str] = Query(None, description="hengpan_a / hengpan_u / platform_a / platform_u"),
        frequency: Optional[Literal["60", "d", "1h"]] = Query(None, description="精确周期，如 60、d、1h；给了它就忽略 intraday"),
        intraday: bool = Query(True, description="只看日内周期（60 分钟与 1 小时），历史页默认开启"),
        status: Optional[Literal["completed", "cancelled", "failed"]] = Query(None, description="completed / cancelled / failed"),
        date_from: Optional[date] = Query(None, description="扫描日下界，含"),
        date_to: Optional[date] = Query(None, description="扫描日上界，含"),
        code: Optional[str] = Query(None, description="只看命中过这个标的的扫描"),
        view: Literal["runs", "symbols"] = Query("runs"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200)):
    if kind and kind not in KIND_SPECS:
        raise HTTPException(status_code=422, detail=f"未知页面类型：{kind}")
    if market and market not in ("a", "crypto"):
        raise HTTPException(status_code=422, detail=f"未知市场：{market}")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="起始扫描日不能晚于结束扫描日")
    query = store.list_symbols if view == 'symbols' else store.list_runs
    return query(market=market, kind=kind, frequency=frequency,
                           intraday_only=intraday, status=status, date_from=date_from.isoformat() if date_from else None,
                           date_to=date_to.isoformat() if date_to else None, code=code, page=page, page_size=page_size)


@router.get("/history/overview", tags=["扫描历史"], summary="历史库总览",
            description="总条数、入选总数、K 线总体积和按页面分组的统计，供容量提醒使用。")
def history_overview():
    summary = store.overview()
    summary["kinds"] = [{"kind": kind, "label": spec["label"], "market": spec["market"]}
                        for kind, spec in KIND_SPECS.items()]
    summary["intraday_frequencies"] = list(db.INTRADAY_FREQUENCIES)
    return summary


@router.get("/history/codes/{code}", tags=["扫描历史"], summary="标的的历史出现情况",
            description="这个标的在历史扫描里命中过哪几次、每次命中几组规则。建表之后才做得到的跨扫描查询。")
def history_code_appearances(
        code: str = Path(description="股票代码或交易对，如 sh.600519、BTCUSDT"),
        limit: int = Query(50, ge=1, le=500)):
    return store.code_appearances(code, limit=limit)


@router.post("/history/cleanup", tags=["扫描历史"], summary="清理历史",
             description="按条数、天数或 K 线总体积清理，三种策略必须且只能选一种。置顶记录永不删除。")
def cleanup_history(request: HistoryCleanupRequest):
    if request.kind and request.kind not in KIND_SPECS:
        raise HTTPException(status_code=422, detail=f"未知页面类型：{request.kind}")
    try:
        return store.cleanup_runs(keep_count=request.keep_count, keep_days=request.keep_days,
                                  max_kline_bytes=request.max_kline_bytes, kind=request.kind,
                                  dry_run=not request.apply)
    except ValueError as error:
        raise HTTPException(status_code=422,
                            detail="keep_count、keep_days、max_kline_bytes 必须三选一，且为正整数") from error


@router.get("/history/{run_id}", tags=["扫描历史"], summary="扫描历史详情",
            description="一次扫描的参数、统计和全部入选标的。每条结果带 rule_count（命中几组规则）；"
                        "kline_data 为空数组，看图请用 K 线接口按标的取。",
            responses={404: {"description": "历史记录不存在"}})
def history_detail(run_id: str = Path(description="扫描记录 ID")):
    payload = store.get_run(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"历史记录不存在：{run_id}")
    return payload


@router.get("/history/{run_id}/kline/{code}", tags=["扫描历史"], summary="历史 K 线",
            description="按需读一只标的在这次扫描时的 K 线。",
            responses={404: {"description": "这次扫描没有该标的的 K 线"}})
def history_kline(run_id: str = Path(description="扫描记录 ID"),
                        code: str = Path(description="股票代码或交易对")):
    try:
        if store.get_run(run_id, with_hits=False) is None:
            raise HTTPException(status_code=404, detail="历史记录不存在")
        payload = store.get_kline(run_id, code)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="无效的记录或标的 ID") from error
    if payload is None:
        raise HTTPException(status_code=404, detail=f"没有 {code} 的 K 线快照")
    return {"run_id": run_id, "code": code, "kline_data": payload}


@router.patch("/history/{run_id}", tags=["扫描历史"], summary="修改历史记录",
              description="改备注或置顶标记。两者都留空视为无操作。",
              responses={404: {"description": "历史记录不存在"}})
def update_history(request: HistoryUpdateRequest,
                         run_id: str = Path(description="扫描记录 ID")):
    payload = store.update_run(run_id, note=request.note, pinned=request.pinned)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"历史记录不存在：{run_id}")
    return payload


@router.delete("/history/{run_id}", tags=["扫描历史"], summary="删除历史记录",
               description="删除一次扫描的记录、入选清单和 K 线文件。",
               responses={404: {"description": "历史记录不存在"}})
def delete_history(run_id: str = Path(description="扫描记录 ID")):
    if not store.delete_run(run_id):
        raise HTTPException(status_code=404, detail=f"历史记录不存在：{run_id}")
    return {"run_id": run_id, "history_id": run_id, "deleted": True}
