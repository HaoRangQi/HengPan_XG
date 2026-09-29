"""
四个扫描页面的快照格式各不相同，这里是唯一一处知道差异的地方。

每个页面登记一条 KIND_SPEC，说明它的市场、周期怎么取、参数藏在哪个键、
结果里的标的字段叫什么。store.py 只跟 KIND_SPECS 打交道，不出现任何页面名分支。

翻译只做投影，不丢信息：结果的完整原始字典存进 scan_hit.detail_json，
读回时原样返回，前端拿到的结构和以前直接读 JSON 快照完全一致。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional


def _amplitude_of(hit: Dict[str, Any]) -> Optional[float]:
    value = hit.get("amplitude")
    return float(value) if isinstance(value, (int, float)) else None


def _hengpan_rule_summary(hit: Dict[str, Any]) -> Dict[str, Any]:
    """横盘系：matches 是 {规则组 id: 该组的命中详情}，命中组数就是它的键数。"""
    matches = hit.get("matches") or {}
    rule_ids = [str(key) for key in matches]
    return {
        "matched_rules": rule_ids,
        "rule_count": len(rule_ids),
        # 任意一组整体口径通过就算整体口径入选，实体口径同理
        "passed_full": int(any(match.get("passed_full") for match in matches.values())),
        "passed_body": int(any(match.get("passed_body") for match in matches.values())),
    }


def _platform_rule_summary(hit: Dict[str, Any]) -> Dict[str, Any]:
    """平台系：没有规则组，命中的是窗口期；selection_reasons 的键就是命中窗口。"""
    reasons = hit.get("selection_reasons") or {}
    windows = [str(key) for key in reasons] or [str(w) for w in (hit.get("platform_windows") or [])]
    return {
        "matched_rules": windows,
        "rule_count": len(windows),
        "passed_full": None,
        "passed_body": None,
    }


KIND_SPECS: Dict[str, Dict[str, Any]] = {
    "hengpan_a": {
        "label": "横盘-A",
        "market": "a",
        "code_key": "code",
        "name_key": "name",
        "group_key": "industry",
        # 参数在 params 里，扫描时周期可选 60 或 d
        "params_key": "params",
        "frequency_default": "d",
        "rule_summary": _hengpan_rule_summary,
        # 参数指纹只看真正决定结果的字段
        "hash_keys": ("rules", "markets", "frequency", "scan_date"),
    },
    "hengpan_u": {
        "label": "横盘-U",
        "market": "crypto",
        "code_key": "symbol",
        "name_key": "base_asset",
        "group_key": "category_label",
        "params_key": "params",
        "frequency_default": "1h",
        "rule_summary": _hengpan_rule_summary,
        "hash_keys": ("rules", "categories", "frequency", "scan_date"),
    },
    "platform_a": {
        "label": "平台-A",
        "market": "a",
        "code_key": "code",
        "name_key": "name",
        "group_key": "industry",
        # 平台-A 历史上把同一份参数存了 config 和 parameters 两份，统一收进 params
        "params_key": "config",
        "frequency_default": "d",
        "rule_summary": _platform_rule_summary,
        "hash_keys": ("windows", "markets", "frequency", "data_source"),
    },
    "platform_u": {
        "label": "平台-U",
        "market": "crypto",
        "code_key": "code",
        "name_key": "name",
        "group_key": "category_label",
        "params_key": "request",
        "frequency_default": "1h",
        "rule_summary": _platform_rule_summary,
        "hash_keys": ("windows", "categories", "category_params"),
    },
}


def spec_of(kind: str) -> Dict[str, Any]:
    spec = KIND_SPECS.get(kind)
    if spec is None:
        raise ValueError(f"unknown scan kind: {kind}")
    return spec


def params_hash(kind: str, params: Dict[str, Any]) -> str:
    """所有请求参数参与指纹，避免不同阈值或股票池被误标为同参数重扫。"""
    spec_of(kind)
    text = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(f"{kind}|{text}".encode("utf-8")).hexdigest()[:16]


# scan_run 有专门列的字段，剩下的一律进 extra_json
_RUN_COLUMNS = {
    "history_id", "task_id", "run_id", "kind", "market", "frequency", "scan_date", "status",
    "created_at", "completed_at", "saved_at", "scanned", "total", "found",
    "params", "rules", "stats", "message", "error", "note", "pinned",
    "results", "result", "config", "parameters", "request",
}


def to_run(kind: str, run_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """把一份快照拆成 scan_run 的字段。不含 hits。"""
    spec = spec_of(kind)
    params = snapshot.get(spec["params_key"]) or snapshot.get("params") or {}
    frequency = (snapshot.get("frequency") or params.get("frequency")
                 or spec["frequency_default"])
    return {
        "run_id": run_id,
        "kind": kind,
        "market": spec["market"],
        "frequency": str(frequency),
        "scan_date": snapshot.get("scan_date"),
        "status": snapshot.get("status") or "completed",
        "created_at": snapshot.get("created_at"),
        "completed_at": snapshot.get("completed_at"),
        "scanned": int(snapshot.get("scanned") or 0),
        "total": int(snapshot.get("total") or 0),
        "found": int(snapshot.get("found") or 0),
        "params": params,
        "rules": snapshot.get("rules") or [],
        "stats": snapshot.get("stats"),
        # 页面独有的字段（data_source、windows、categories…）原样留着，还原时合并回去
        "extra": {key: value for key, value in snapshot.items()
                  if key not in _RUN_COLUMNS},
        "params_hash": params_hash(kind, params),
        "message": snapshot.get("message") or "",
        "error": snapshot.get("error"),
    }


def to_hits(kind: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把结果列表拆成 scan_hit 行，K 线单独摘出来。"""
    spec = spec_of(kind)
    rows = []
    for seq, hit in enumerate(results or []):
        code = hit.get(spec["code_key"]) or hit.get("code") or hit.get("symbol")
        if not code:
            continue
        summary = spec["rule_summary"](hit)
        detail = {key: value for key, value in hit.items() if key != "kline_data"}
        close = hit.get("close", hit.get("last_price"))
        rows.append({
            "code": str(code),
            "seq": seq,
            "name": hit.get(spec["name_key"]) or hit.get("name"),
            "group_label": hit.get(spec["group_key"]),
            "close": float(close) if isinstance(close, (int, float)) else None,
            "amplitude": _amplitude_of(hit),
            "matched_rules": summary["matched_rules"],
            "rule_count": summary["rule_count"],
            "passed_full": summary["passed_full"],
            "passed_body": summary["passed_body"],
            "detail": detail,
            "kline": hit.get("kline_data") or [],
        })
    return rows
