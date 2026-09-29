"""
扫描历史的读写。四个页面共用这一份逻辑，页面差异全部在 adapters.py。

写入：save_run() 一个事务写完 scan_run + scan_hit，K 线按只写文件。
读取：list_runs() 只查 scan_run，不碰 hits 和 K 线；get_run() 带 hits 但不带 K 线；
      看图时 get_kline() 按 (run_id, code) 读一个文件。
"""
from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import time
import threading
from functools import wraps
from typing import Any, Dict, List, Optional

from . import db
from .adapters import KIND_SPECS, params_hash, to_hits, to_run


_LOCK = threading.RLock()


def _locked(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with _LOCK:
            return function(*args, **kwargs)
    return guarded


def _json_safe(value: Any) -> Any:
    """NumPy 标量、非有限浮点都转成能进 JSON 的形式；未知类型退化成字符串。"""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, dict):
        return {str(key): _json_safe(entry) for key, entry in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(entry) for entry in value]
    return str(value)


def _dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(_json_safe(value), ensure_ascii=False, allow_nan=False)


def _loads(text: Optional[str], fallback: Any = None) -> Any:
    if not text:
        return fallback
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return fallback


def _safe_name(value: str) -> str:
    """拒绝目录分隔符和点目录，不通过替换字符制造文件名碰撞。"""
    text = str(value)
    if not text or text in ('.', '..') or any(not (ch.isalnum() or ch in '-_.') for ch in text):
        raise ValueError('invalid history path segment')
    return text


def kline_dir(run_id: str, base_dir: Optional[str] = None) -> str:
    return os.path.join(base_dir or db.KLINE_DIR, _safe_name(run_id))


def _write_klines(run_id: str, rows: List[Dict[str, Any]],
                  base_dir: Optional[str] = None) -> int:
    """一只票一个文件，返回总字节数。写失败只影响看图，不让扫描结果丢失。"""
    target_dir = kline_dir(run_id, base_dir)
    written = 0
    for row in rows:
        payload = row.get("kline") or []
        if not payload:
            continue
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"{_safe_name(row['code'])}.json")
        text = json.dumps(_json_safe(payload), ensure_ascii=False, allow_nan=False)
        fd, temporary = tempfile.mkstemp(prefix=".kline-", suffix=".json", dir=target_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(temporary, path)
            written += len(text.encode("utf-8"))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return written


def _drop_klines(run_id: str, base_dir: Optional[str] = None) -> None:
    target = kline_dir(run_id, base_dir)
    if os.path.isdir(target):
        shutil.rmtree(target)


def rule_keys(run, row):
    """规则按有效参数识别；不同扫描重复命中同一规则不增加规则种数。"""
    rules = {str(rule['id']): rule.get('params', {}) for rule in run['rules']}
    keys = []
    for rule_id in row['matched_rules']:
        if run['kind'].startswith('hengpan'):
            params = dict(rules.get(rule_id, {'unknown_rule': rule_id}))
            mode = params.get('box_type', 'fixed')
            used = ['box_type', 'lookback', 'max_breach']
            used += {'fixed': ['box_height', 'doji_amplitude'],
                     'amplitude': ['amp_multiple', 'max_amplitude'],
                     'tolerant': ['box_height', 'max_consecutive_breach']}.get(mode, [])
            if 'unknown_rule' not in params:
                params = {key: params.get(key) for key in used}
        else:
            params = {key: value for key, value in run['params'].items()
                      if key not in ('windows', 'markets', 'categories', 'symbols', 'scan_date',
                                     'limit_count', 'expected_count', 'data_source')}
            params['window'] = rule_id
        keys.append(params_hash(run['kind'], {**params, 'frequency': run['frequency']}))
    return list(dict.fromkeys(keys))


@_locked
def save_run(kind: str, run_id: str, snapshot: Dict[str, Any], *,
             conn=None, kline_base_dir: Optional[str] = None) -> Dict[str, Any]:
    """写入一次扫描。同 run_id 重复写入覆盖（重启后补写、失败转完成都走这条路）。"""
    _safe_name(run_id)
    snapshot = _json_safe(snapshot)
    run = to_run(kind, run_id, snapshot)
    hits = to_hits(kind, snapshot.get("results") or snapshot.get("result") or [])
    codes = [row['code'] for row in hits]
    for code in codes:
        _safe_name(code)
    if len(set(codes)) != len(codes):
        raise ValueError('duplicate symbol in scan snapshot')
    run['found'] = len(hits)
    if not run['scan_date']:
        dates = [str(hit.get('date') or ((hit.get('kline_data') or [{}])[-1].get('date')) or '')[:10]
                 for hit in snapshot.get('results', snapshot.get('result', [])) or []]
        run['scan_date'] = max(dates, default='') or None
    for row in hits:
        row['rule_keys'] = rule_keys(run, row)

    # 先写独立暂存目录。数据库提交失败时恢复旧目录，不先删除唯一的 K 线副本。
    root = kline_base_dir or db.KLINE_DIR
    os.makedirs(root, exist_ok=True)
    stage = tempfile.mkdtemp(prefix='.pending-', dir=root)
    target = kline_dir(run_id, root)
    backup = os.path.join(stage, 'previous')
    installed = False
    try:
        kline_bytes = _write_klines(run_id, hits, stage)
        os.makedirs(kline_dir(run_id, stage), exist_ok=True)
    except Exception:
        shutil.rmtree(stage)
        raise

    def _write(connection):
        connection.execute("DELETE FROM scan_hit WHERE run_id = ?", (run_id,))
        connection.execute(
            """INSERT OR REPLACE INTO scan_run
               (run_id, kind, market, frequency, scan_date, status, created_at, completed_at,
                saved_at, scanned, total, found, params_json, rules_json, stats_json,
                extra_json, params_hash, message, error, note, pinned, kline_bytes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                       COALESCE((SELECT note FROM scan_run WHERE run_id = ?), NULL),
                       COALESCE((SELECT pinned FROM scan_run WHERE run_id = ?), 0), ?)""",
            (run["run_id"], run["kind"], run["market"], run["frequency"], run["scan_date"],
             run["status"], run["created_at"], run["completed_at"], time.time(),
             run["scanned"], run["total"], run["found"], _dumps(run["params"]),
             _dumps(run["rules"]), _dumps(run["stats"]), _dumps(run["extra"]),
             run["params_hash"], run["message"], run["error"], run_id, run_id, kline_bytes))
        connection.executemany(
            """INSERT INTO scan_hit
               (run_id, code, seq, name, group_label, close, amplitude,
                matched_rules, rule_count, passed_full, passed_body, detail_json, rule_keys_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(run_id, row["code"], row["seq"], row["name"], row["group_label"],
              row["close"], row["amplitude"], _dumps(row["matched_rules"]),
              row["rule_count"], row["passed_full"], row["passed_body"],
              _dumps(row["detail"]), _dumps(row['rule_keys'])) for row in hits])

    def _commit(connection):
        nonlocal installed
        try:
            _write(connection)
            if os.path.exists(target):
                os.replace(target, backup)
            os.replace(kline_dir(run_id, stage), target)
            installed = True
            connection.commit()
        except Exception:
            connection.rollback()
            if installed:
                shutil.rmtree(target)
            if os.path.exists(backup):
                os.replace(backup, target)
            raise

    try:
        if conn is not None:
            _commit(conn)
        else:
            with db.open_db() as connection:
                _commit(connection)
    finally:
        shutil.rmtree(stage)
    return run_metadata_of(run_id, conn=conn)


def _run_row_to_metadata(row, duplicate_count: int = 0) -> Dict[str, Any]:
    params = _loads(row["params_json"], {}) or {}
    extra = _loads(row["extra_json"], {}) or {}
    stats = _loads(row["stats_json"])
    rule_stats = ((stats or {}).get("rules") or {}) if isinstance(stats, dict) else {}
    return {
        "run_id": row["run_id"],
        # 老接口按 history_id 取值，保留同名字段，前端不需要改
        "history_id": row["run_id"],
        "task_id": row["run_id"],
        "kind": row["kind"],
        "kind_label": KIND_SPECS[row["kind"]]["label"] if row["kind"] in KIND_SPECS else row["kind"],
        "market": row["market"],
        "frequency": row["frequency"],
        "scan_date": row["scan_date"],
        "status": row["status"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "saved_at": row["saved_at"],
        "scanned": row["scanned"],
        "total": row["total"],
        "found": row["found"],
        "result_count": row["found"],
        "message": row["message"] or "",
        "note": row["note"],
        "pinned": bool(row["pinned"]),
        "kline_bytes": row["kline_bytes"],
        "params_hash": row["params_hash"],
        # 同参数重扫的份数（含自己）；1 表示没有重复
        "duplicate_count": duplicate_count,
        "rules": _loads(row["rules_json"], []) or [],
        "markets": params.get("markets", []),
        "categories": params.get("categories", extra.get("categories", [])),
        "windows": params.get("windows", extra.get("windows", [])),
        "passed_full_by_rule": {rule_id: stat.get("passed_full", 0)
                                for rule_id, stat in rule_stats.items()},
    }


_LIST_COLUMNS = ("run_id, kind, market, frequency, scan_date, status, created_at, completed_at, "
                 "saved_at, scanned, total, found, params_json, rules_json, stats_json, "
                 "extra_json, params_hash, message, note, pinned, kline_bytes")


def _filters(*, market=None, kind=None, frequency=None, intraday_only=False,
             status=None, date_from=None, date_to=None, code=None, prefix=''):
    clauses, args = [], []
    for column, value in (('market', market), ('kind', kind), ('frequency', frequency), ('status', status)):
        if value:
            clauses.append(f'{prefix}{column} = ?')
            args.append(value)
    if not frequency and intraday_only:
        clauses.append(f"{prefix}frequency IN ('60', '1h')")
    for operator, value in (('>=', date_from), ('<=', date_to)):
        if value:
            clauses.append(f'{prefix}scan_date {operator} ?')
            args.append(value)
    if code:
        clauses.append(f'{prefix}run_id IN (SELECT run_id FROM scan_hit WHERE code = ?)')
        args.append(code)
    return ('WHERE ' + ' AND '.join(clauses) if clauses else ''), args


@_locked
def list_symbols(*, market=None, kind=None, frequency=None, intraday_only=True,
                 status=None, date_from=None, date_to=None, code=None,
                 page=1, page_size=20, conn=None):
    """当前筛选范围内一标的一行，重复扫描不重复计算规则种数。"""
    where, args = _filters(market=market, kind=kind, frequency=frequency,
                           intraday_only=intraday_only, status=status, date_from=date_from,
                           date_to=date_to, code=None, prefix='r.')
    if code:
        where += (' AND ' if where else 'WHERE ') + 'h.code = ?'
        args.append(code)
    cte = f'''WITH hits AS (
        SELECT h.code, h.name, h.group_label, h.close, h.amplitude, h.rule_keys_json,
               r.run_id, r.market, r.kind, r.frequency, r.scan_date, r.saved_at,
               ROW_NUMBER() OVER (PARTITION BY r.market, h.code
                                  ORDER BY r.saved_at DESC, r.run_id DESC) AS row_num
        FROM scan_hit h JOIN scan_run r ON r.run_id = h.run_id {where}
    ), grouped AS (
        SELECT market, code, COUNT(*) AS run_count, MAX(saved_at) AS last_seen
        FROM hits GROUP BY market, code
    )'''
    page, page_size = max(1, int(page)), max(1, min(200, int(page_size)))

    def query(connection):
        total = connection.execute(cte + ' SELECT COUNT(*) FROM grouped', args).fetchone()[0]
        rows = connection.execute(cte + '''
            SELECT g.*, h.run_id, h.name, h.group_label, h.close, h.amplitude,
                   h.kind, h.frequency, h.scan_date,
                   (SELECT COUNT(DISTINCT j.value) FROM hits h2, json_each(h2.rule_keys_json) j
                    WHERE h2.code = g.code AND h2.market = g.market) AS rule_count
            FROM grouped g JOIN hits h ON h.code = g.code AND h.market = g.market AND h.row_num = 1
            ORDER BY g.last_seen DESC, g.market, g.code LIMIT ? OFFSET ?''',
            (*args, page_size, (page - 1) * page_size)).fetchall()
        return {'symbols': [dict(row) for row in rows], 'total': total,
                'page': page, 'page_size': page_size}
    if conn is not None:
        return query(conn)
    with db.open_db() as connection:
        return query(connection)


@_locked
def list_runs(*, market: Optional[str] = None, kind: Optional[str] = None,
              frequency: Optional[str] = None, intraday_only: bool = False,
              status: Optional[str] = None, date_from: Optional[str] = None,
              date_to: Optional[str] = None, code: Optional[str] = None,
              page: int = 1, page_size: int = 20, conn=None) -> Dict[str, Any]:
    """按条件分页列出扫描记录。只查 scan_run，不读 hits，不读 K 线。"""
    where, args = _filters(market=market, kind=kind, frequency=frequency,
                           intraday_only=intraday_only, status=status, date_from=date_from,
                           date_to=date_to, code=code)
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))

    def _query(connection):
        total = connection.execute(
            f"SELECT COUNT(*) FROM scan_run {where}", args).fetchone()[0]
        rows = connection.execute(
            f"SELECT {_LIST_COLUMNS} FROM scan_run {where} "
            "ORDER BY pinned DESC, saved_at DESC, run_id DESC LIMIT ? OFFSET ?",
            (*args, page_size, (page - 1) * page_size)).fetchall()
        # 同参数重扫的份数，一次查完，避免每行一条 SQL
        hashes = [row["params_hash"] for row in rows if row["params_hash"]]
        counts: Dict[str, int] = {}
        if hashes:
            marks = ",".join("?" * len(hashes))
            counts = {entry["params_hash"]: entry["n"] for entry in connection.execute(
                f"SELECT params_hash, COUNT(*) AS n FROM scan_run "
                f"WHERE params_hash IN ({marks}) GROUP BY params_hash", hashes)}
        return {
            "histories": [_run_row_to_metadata(row, counts.get(row["params_hash"], 1))
                          for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    if conn is not None:
        return _query(conn)
    with db.open_db() as connection:
        return _query(connection)


def _hit_row_to_dict(row) -> Dict[str, Any]:
    """还原成页面结果的原始结构，再补上表里算好的摘要字段。"""
    detail = _loads(row["detail_json"], {}) or {}
    detail["matched_rules"] = _loads(row["matched_rules"], []) or []
    detail["rule_count"] = row["rule_count"]
    # K 线按需取，这里留空数组：前端拿到空数组会走「点开再取图」的分支
    detail.setdefault("kline_data", [])
    return detail


@_locked
def get_run(run_id: str, *, conn=None, with_hits: bool = True) -> Optional[Dict[str, Any]]:
    """一次扫描的完整记录：元数据 + 参数 + 统计 + 入选清单，不含 K 线。"""
    def _query(connection):
        row = connection.execute(
            f"SELECT {_LIST_COLUMNS}, error FROM scan_run WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        duplicates = connection.execute(
            "SELECT COUNT(*) FROM scan_run WHERE params_hash = ?",
            (row["params_hash"],)).fetchone()[0] if row["params_hash"] else 1
        payload = _run_row_to_metadata(row, duplicates)
        payload["params"] = _loads(row["params_json"], {}) or {}
        payload["stats"] = _loads(row["stats_json"])
        payload["error"] = row["error"]
        payload.update(_loads(row["extra_json"], {}) or {})
        if with_hits:
            hits = [_hit_row_to_dict(entry) for entry in connection.execute(
                "SELECT code, seq, matched_rules, rule_count, detail_json "
                "FROM scan_hit WHERE run_id = ? ORDER BY seq", (run_id,))]
            payload["results"] = hits
            # 平台-A 的老接口同时给 results 和 result，保留两个键
            payload["result"] = hits
        return payload

    if conn is not None:
        return _query(conn)
    with db.open_db() as connection:
        return _query(connection)


@_locked
def get_kline(run_id: str, code: str, base_dir: Optional[str] = None) -> Optional[List[Any]]:
    """按需读一只票的 K 线。文件不存在返回 None，由调用方决定回落方式。"""
    path = os.path.join(kline_dir(run_id, base_dir), f"{_safe_name(code)}.json")
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


@_locked
def update_run(run_id: str, *, note: Optional[str] = None,
               pinned: Optional[bool] = None, conn=None) -> Optional[Dict[str, Any]]:
    """改备注和置顶标记。两个都不传视为无操作，仍返回当前元数据。"""
    fields, args = [], []
    if note is not None:
        fields.append("note = ?")
        args.append(note)
    if pinned is not None:
        fields.append("pinned = ?")
        args.append(int(pinned))

    def _write(connection):
        if connection.execute("SELECT 1 FROM scan_run WHERE run_id = ?",
                              (run_id,)).fetchone() is None:
            return None
        if fields:
            connection.execute(f"UPDATE scan_run SET {', '.join(fields)} WHERE run_id = ?",
                               (*args, run_id))
            connection.commit()
        return get_run(run_id, conn=connection, with_hits=False)

    if conn is not None:
        return _write(conn)
    with db.open_db() as connection:
        return _write(connection)


@_locked
def delete_run(run_id: str, *, conn=None, kline_base_dir: Optional[str] = None) -> bool:
    def _write(connection):
        cursor = connection.execute("DELETE FROM scan_run WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM scan_hit WHERE run_id = ?", (run_id,))
        connection.commit()
        return cursor.rowcount > 0

    if conn is not None:
        deleted = _write(conn)
    else:
        with db.open_db() as connection:
            deleted = _write(connection)
    if deleted:
        _drop_klines(run_id, kline_base_dir)
    return deleted


@_locked
def cleanup_runs(*, keep_count: Optional[int] = None, keep_days: Optional[int] = None,
                 max_kline_bytes: Optional[int] = None, kind: Optional[str] = None,
                 dry_run: bool = False, conn=None, kline_base_dir: Optional[str] = None) -> Dict[str, int]:
    """
    按数量、天数或总体积清理，三种策略必须且只能选一种。
    置顶记录永不删除，也不占用保留额度之外的判断。
    """
    policies = [keep_count is not None, keep_days is not None, max_kline_bytes is not None]
    if sum(policies) != 1:
        raise ValueError("exactly one cleanup policy is required")
    for name, value in (("keep_count", keep_count), ("keep_days", keep_days),
                        ("max_kline_bytes", max_kline_bytes)):
        if value is not None and (isinstance(value, bool) or value < 1):
            raise ValueError(f"{name} must be a positive integer")

    def _select(connection):
        clauses = ["pinned = 0"]
        args: List[Any] = []
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        rows = connection.execute(
            f"SELECT run_id, saved_at, kline_bytes FROM scan_run "
            f"WHERE {' AND '.join(clauses)} ORDER BY saved_at DESC, run_id DESC", args).fetchall()
        if keep_count is not None:
            return [row["run_id"] for row in rows[keep_count:]]
        if keep_days is not None:
            cutoff = time.time() - keep_days * 86400
            return [row["run_id"] for row in rows if (row["saved_at"] or 0) < cutoff]
        # 按体积：从新到旧累加，超出预算的部分删掉
        pinned_where = "WHERE pinned = 1" + (" AND kind = ?" if kind else "")
        used = connection.execute(
            f"SELECT COALESCE(SUM(kline_bytes), 0) FROM scan_run {pinned_where}", args).fetchone()[0]
        victims = []
        for row in rows:
            used += row["kline_bytes"] or 0
            if used > max_kline_bytes:
                victims.append(row["run_id"])
        return victims

    def _write(connection):
        victims = _select(connection)
        for run_id in ([] if dry_run else victims):
            connection.execute("DELETE FROM scan_run WHERE run_id = ?", (run_id,))
            connection.execute("DELETE FROM scan_hit WHERE run_id = ?", (run_id,))
        connection.commit()
        kept = connection.execute("SELECT COUNT(*) FROM scan_run" + (" WHERE kind = ?" if kind else ""),
                                  (kind,) if kind else ()).fetchone()[0]
        if dry_run:
            kept -= len(victims)
        return victims, kept

    if conn is not None:
        victims, kept = _write(conn)
    else:
        with db.open_db() as connection:
            victims, kept = _write(connection)
    for run_id in ([] if dry_run else victims):
        _drop_klines(run_id, kline_base_dir)
    return {"deleted": len(victims), "kept": kept}


@_locked
def overview(*, conn=None) -> Dict[str, Any]:
    """历史库总览：总条数、总体积、按页面分组的条数，供容量提醒使用。"""
    def _query(connection):
        row = connection.execute(
            "SELECT COUNT(*) AS runs, COALESCE(SUM(kline_bytes), 0) AS bytes, "
            "MIN(saved_at) AS oldest, MAX(saved_at) AS newest FROM scan_run").fetchone()
        by_kind = [{"kind": entry["kind"],
                    "kind_label": KIND_SPECS[entry["kind"]]["label"]
                    if entry["kind"] in KIND_SPECS else entry["kind"],
                    "runs": entry["runs"], "kline_bytes": entry["bytes"]}
                   for entry in connection.execute(
                       "SELECT kind, COUNT(*) AS runs, COALESCE(SUM(kline_bytes), 0) AS bytes "
                       "FROM scan_run GROUP BY kind ORDER BY kind")]
        hits = connection.execute("SELECT COUNT(*) FROM scan_hit").fetchone()[0]
        return {
            "runs": row["runs"],
            "hits": hits,
            "kline_bytes": row["bytes"],
            "oldest_saved_at": row["oldest"],
            "newest_saved_at": row["newest"],
            "by_kind": by_kind,
            "db_path": db.DB_PATH,
            "kline_dir": db.KLINE_DIR,
        }

    if conn is not None:
        return _query(conn)
    with db.open_db() as connection:
        return _query(connection)


def code_appearances(code: str, *, limit: int = 50, conn=None) -> Dict[str, Any]:
    """
    一个标的在历史里的出现情况：哪几次扫描命中过、每次命中几组规则。
    这是建表之后才做得到的查询，JSON 快照时代只能整份读出来再自己比对。
    """
    def _query(connection):
        rows = connection.execute(
            "SELECT h.run_id, h.name, h.group_label, h.rule_count, h.matched_rules, "
            "       h.close, h.amplitude, r.kind, r.market, r.frequency, r.scan_date, "
            "       r.saved_at, r.status "
            "FROM scan_hit h JOIN scan_run r ON r.run_id = h.run_id "
            "WHERE h.code = ? ORDER BY r.saved_at DESC LIMIT ?",
            (code, max(1, min(500, int(limit))))).fetchall()
        return {
            "code": code,
            "appearances": [{
                "run_id": row["run_id"],
                "kind": row["kind"],
                "kind_label": KIND_SPECS[row["kind"]]["label"]
                if row["kind"] in KIND_SPECS else row["kind"],
                "market": row["market"],
                "frequency": row["frequency"],
                "scan_date": row["scan_date"],
                "saved_at": row["saved_at"],
                "status": row["status"],
                "name": row["name"],
                "group_label": row["group_label"],
                "close": row["close"],
                "amplitude": row["amplitude"],
                "rule_count": row["rule_count"],
                "matched_rules": _loads(row["matched_rules"], []) or [],
            } for row in rows],
            "run_count": len(rows),
        }

    if conn is not None:
        return _query(conn)
    with db.open_db() as connection:
        return _query(connection)


def run_metadata_of(run_id: str, *, conn=None) -> Dict[str, Any]:
    """save_run 的返回值：和老的 history_metadata() 对齐，不含 hits。"""
    payload = get_run(run_id, conn=conn, with_hits=False)
    return payload or {"run_id": run_id, "history_id": run_id}


def hit_codes(run_id: str, *, conn=None) -> List[str]:
    def _query(connection):
        return [row["code"] for row in connection.execute(
            "SELECT code FROM scan_hit WHERE run_id = ? ORDER BY seq", (run_id,))]

    if conn is not None:
        return _query(conn)
    with db.open_db() as connection:
        return _query(connection)
