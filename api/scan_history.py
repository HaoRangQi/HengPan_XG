"""平台-A 的扫描快照。存储已统一到 api/history/，这里只剩一层薄封装。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .history import legacy, store

KIND = "platform_a"


def save_scan_history(history_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return store.save_run(KIND, history_id, snapshot)


def history_metadata(history_id: str) -> Dict[str, Any]:
    return store.run_metadata_of(history_id)


def list_scan_histories() -> List[Dict[str, Any]]:
    return legacy.list_all(KIND)


def get_scan_history(history_id: str) -> Optional[Dict[str, Any]]:
    return legacy.get(KIND, history_id)


def delete_scan_history(history_id: str) -> bool:
    return legacy.delete(KIND, history_id)
