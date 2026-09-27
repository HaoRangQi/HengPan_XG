"""Small JSON-backed store for completed and cancelled scan snapshots."""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional


_BASE_DIR = os.path.join(os.path.dirname(__file__), "data", "scan_history")
_LOCK = threading.Lock()


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def _path(history_id: str) -> str:
    safe_id = "".join(ch for ch in str(history_id) if ch.isalnum() or ch in "-_ .")
    if not safe_id or safe_id != str(history_id):
        raise ValueError("invalid history id")
    return os.path.join(_BASE_DIR, f"{safe_id}.json")


def save_scan_history(history_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Persist one snapshot atomically and return its metadata."""
    os.makedirs(_BASE_DIR, exist_ok=True)
    payload = _json_safe(dict(snapshot))
    payload["history_id"] = history_id
    payload.setdefault("saved_at", time.time())
    target = _path(history_id)
    with _LOCK:
        fd, temporary = tempfile.mkstemp(prefix=".scan-", suffix=".json", dir=_BASE_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, allow_nan=False)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return history_metadata(payload)


def history_metadata(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    results = snapshot.get("results", snapshot.get("result", [])) or []
    return {
        "history_id": snapshot.get("history_id"),
        "task_id": snapshot.get("task_id"),
        "status": snapshot.get("status"),
        "saved_at": snapshot.get("saved_at"),
        "created_at": snapshot.get("created_at"),
        "completed_at": snapshot.get("completed_at"),
        "frequency": snapshot.get("frequency", "d"),
        "windows": snapshot.get("windows", []),
        "scanned": snapshot.get("scanned", 0),
        "total": snapshot.get("total", 0),
        "found": snapshot.get("found", len(results)),
        "result_count": len(results),
        "message": snapshot.get("message", ""),
    }


def list_scan_histories() -> List[Dict[str, Any]]:
    os.makedirs(_BASE_DIR, exist_ok=True)
    records: List[Dict[str, Any]] = []
    with _LOCK:
        for filename in os.listdir(_BASE_DIR):
            if not filename.endswith(".json"):
                continue
            try:
                with open(os.path.join(_BASE_DIR, filename), encoding="utf-8") as handle:
                    records.append(history_metadata(json.load(handle)))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
    return sorted(records, key=lambda item: item.get("saved_at") or 0, reverse=True)


def get_scan_history(history_id: str) -> Optional[Dict[str, Any]]:
    try:
        target = _path(history_id)
    except ValueError:
        return None
    try:
        with _LOCK, open(target, encoding="utf-8") as handle:
            payload = json.load(handle)
        payload.setdefault("results", payload.get("result", []))
        payload.setdefault("result", payload.get("results", []))
        return payload
    except (OSError, ValueError, json.JSONDecodeError):
        return None
