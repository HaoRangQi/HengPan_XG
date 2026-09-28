"""
横盘-U 的扫描快照。

格式和横盘-A 完全一致，存储逻辑直接复用 api/hengpan/history.py，只换一个目录，
避免两份文件读写代码各自演化。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..hengpan import history as _store

BASE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "crypto_hengpan_history"))


def save_history(history_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return _store.save_history(history_id, snapshot, base_dir=BASE_DIR)


def list_histories() -> List[Dict[str, Any]]:
    return _store.list_histories(base_dir=BASE_DIR)


def get_history(history_id: str) -> Optional[Dict[str, Any]]:
    return _store.get_history(history_id, base_dir=BASE_DIR)


def delete_history(history_id: str) -> bool:
    return _store.delete_history(history_id, base_dir=BASE_DIR)


def cleanup_histories(*, keep_count: Optional[int] = None,
                      keep_days: Optional[int] = None) -> Dict[str, int]:
    return _store.cleanup_histories(keep_count=keep_count, keep_days=keep_days, base_dir=BASE_DIR)
