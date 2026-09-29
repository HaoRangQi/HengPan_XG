"""加密平台扫描历史。存储已统一到 api/history/，这里只剩一层薄封装。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..history import legacy, store

KIND = "platform_u"


def save(history_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return store.save_run(KIND, history_id, snapshot)


def metadata(history_id: str) -> Dict[str, Any]:
    return store.run_metadata_of(history_id)


def list_all() -> List[Dict[str, Any]]:
    return legacy.list_all(KIND)


def get(history_id: str) -> Optional[Dict[str, Any]]:
    return legacy.get(KIND, history_id)


def delete(history_id: str) -> bool:
    return legacy.delete(KIND, history_id)
