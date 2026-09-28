"""加密平台扫描历史快照，和 A 股扫描历史分开保存。"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "crypto_platform_history")
LOCK = threading.Lock()


def _json_safe(value: Any) -> Any:
    """Convert pandas/NumPy scalar values and non-finite numbers for JSON."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    # NumPy scalars expose item(), while keeping NumPy out of this module's
    # runtime dependencies lets history listing work in lightweight tools.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _path(history_id: str) -> str:
    safe = "".join(ch for ch in str(history_id) if ch.isalnum() or ch in "-_. ")
    if not safe or safe != str(history_id):
        raise ValueError("invalid history id")
    return os.path.join(BASE_DIR, f"{safe}.json")


def save(history_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(BASE_DIR, exist_ok=True)
    payload = _json_safe(dict(snapshot))
    payload["history_id"] = history_id
    payload.setdefault("saved_at", time.time())
    target = _path(history_id)
    with LOCK:
        fd, temporary = tempfile.mkstemp(prefix=".scan-", suffix=".json", dir=BASE_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, allow_nan=False)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return metadata(payload)


def metadata(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    results = snapshot.get("results") or []
    return {"history_id": snapshot.get("history_id"), "task_id": snapshot.get("task_id"),
            "status": snapshot.get("status"), "saved_at": snapshot.get("saved_at"),
            "created_at": snapshot.get("created_at"), "completed_at": snapshot.get("completed_at"),
            "categories": snapshot.get("categories", []), "windows": snapshot.get("windows", []),
            "scanned": snapshot.get("scanned", 0), "total": snapshot.get("total", 0),
            "result_count": len(results), "message": snapshot.get("message", "")}


def list_all() -> List[Dict[str, Any]]:
    os.makedirs(BASE_DIR, exist_ok=True)
    records = []
    with LOCK:
        for filename in os.listdir(BASE_DIR):
            if not filename.endswith(".json"):
                continue
            try:
                with open(os.path.join(BASE_DIR, filename), encoding="utf-8") as handle:
                    records.append(metadata(json.load(handle)))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
    return sorted(records, key=lambda item: item.get("saved_at") or 0, reverse=True)


def get(history_id: str) -> Optional[Dict[str, Any]]:
    try:
        target = _path(history_id)
    except ValueError:
        return None
    try:
        with LOCK, open(target, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def delete(history_id: str) -> bool:
    try:
        target = _path(history_id)
    except ValueError:
        return False
    with LOCK:
        try:
            os.remove(target)
        except FileNotFoundError:
            return False
    return True
