"""
横盘选股的扫描快照。存储已统一到 api/history/，这里只剩一层薄封装：
把 kind 固定成 hengpan_a，保留原来的函数名和返回结构，调用方不用改。

横盘-U 传 kind="hengpan_u"（见 api/crypto/hengpan_history.py），其余调用方用默认值。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..history import legacy, store

KIND = "hengpan_a"


def save_history(history_id: str, snapshot: Dict[str, Any],
                 kind: Optional[str] = None) -> Dict[str, Any]:
    return store.save_run(kind or KIND, history_id, snapshot)


def history_metadata(history_id: str, kind: Optional[str] = None) -> Dict[str, Any]:
    return store.run_metadata_of(history_id)


def list_histories(kind: Optional[str] = None) -> List[Dict[str, Any]]:
    # 老接口不分页、不筛周期，一次给全部；新历史页走 /api/history
    return legacy.list_all(kind or KIND)


def get_history(history_id: str, kind: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return legacy.get(kind or KIND, history_id)


def delete_history(history_id: str, kind: Optional[str] = None) -> bool:
    return legacy.delete(kind or KIND, history_id)


def cleanup_histories(*, keep_count: Optional[int] = None,
                      keep_days: Optional[int] = None,
                      kind: Optional[str] = None) -> Dict[str, int]:
    return store.cleanup_runs(keep_count=keep_count, keep_days=keep_days,
                              kind=kind or KIND)
