"""
横盘-U 的扫描快照。存储和横盘-A 共用 api/history/，只换一个 kind。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..hengpan import history as _store

KIND = "hengpan_u"


def save_history(history_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _store.save_history(history_id, snapshot, kind=KIND)


def list_histories() -> List[Dict[str, Any]]:
    return _store.list_histories(kind=KIND)


def get_history(history_id: str) -> Optional[Dict[str, Any]]:
    return _store.get_history(history_id, kind=KIND)


def delete_history(history_id: str) -> bool:
    return _store.delete_history(history_id, kind=KIND)


def cleanup_histories(*, keep_count: Optional[int] = None,
                      keep_days: Optional[int] = None) -> Dict[str, int]:
    return _store.cleanup_histories(keep_count=keep_count, keep_days=keep_days, kind=KIND)
