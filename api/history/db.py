"""
扫描历史库的建表和连接管理。

独立的 history.db，不和行情库 market.db / crypto.db 混在一起：行情按板块分表、可以随时
重新同步；扫描历史是不可再生的记录，生命周期完全不同。

两张表 + 一处文件：
  scan_run  一次扫描一行，列是「为了筛选和排序」的投影，extra_json 兜住各页面独有的字段
  scan_hit  一条入选一行，detail_json 存这条结果的完整原始字段（不含 K 线），可无损还原
  K 线      落在 data/scan_kline/{run_id}/{code}.json，一只票一个文件。列表和详情都不碰它，
            只有点开看图时按路径读一只票；kline_bytes 记在 scan_run 上供容量提醒使用。
"""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "history.db"))

# K 线文件根目录，和 history.db 同级
KLINE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "scan_kline"))

# 四个扫描页面。市场和默认周期在 adapters.KIND_SPECS 里登记
KINDS = ("hengpan_a", "hengpan_u", "platform_a", "platform_u")

# 「日内」指哪些周期：A 股 60 分钟线、加密 1 小时线
INTRADAY_FREQUENCIES = ("60", "1h")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS scan_run (
         run_id       TEXT PRIMARY KEY,
         kind         TEXT NOT NULL,
         market       TEXT NOT NULL,
         frequency    TEXT NOT NULL,
         scan_date    TEXT,
         status       TEXT NOT NULL,
         created_at   REAL,
         completed_at REAL,
         saved_at     REAL NOT NULL,
         scanned      INTEGER NOT NULL DEFAULT 0,
         total        INTEGER NOT NULL DEFAULT 0,
         found        INTEGER NOT NULL DEFAULT 0,
         params_json  TEXT,
         rules_json   TEXT,
         stats_json   TEXT,
         extra_json   TEXT,
         params_hash  TEXT,
         message      TEXT,
         error        TEXT,
         note         TEXT,
         pinned       INTEGER NOT NULL DEFAULT 0,
         kline_bytes  INTEGER NOT NULL DEFAULT 0
       )""",
    # detail_json 是这条结果的真值，表列只是投影；主键字段名各页面不同（横盘-U 用 symbol），
    # 差异原样留在 detail_json 里，还原时不需要任何分支
    """CREATE TABLE IF NOT EXISTS scan_hit (
         run_id        TEXT NOT NULL,
         code          TEXT NOT NULL,
         seq           INTEGER NOT NULL,
         name          TEXT,
         group_label   TEXT,
         close         REAL,
         amplitude     REAL,
         matched_rules TEXT,
         rule_count    INTEGER NOT NULL DEFAULT 0,
         passed_full   INTEGER,
         passed_body   INTEGER,
         detail_json   TEXT,
         rule_keys_json TEXT NOT NULL DEFAULT '[]',
         PRIMARY KEY (run_id, code)
       ) WITHOUT ROWID""",
    # 历史页默认「当前市场 + 日内周期 + 按时间倒序」，这条索引覆盖它
    "CREATE INDEX IF NOT EXISTS idx_run_filter ON scan_run(market, kind, frequency, saved_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_run_saved ON scan_run(saved_at DESC)",
    # 识别同参数重扫
    "CREATE INDEX IF NOT EXISTS idx_run_hash ON scan_run(params_hash)",
    # 跨扫描按标的反查：某只票最近出现在哪几次扫描里
    "CREATE INDEX IF NOT EXISTS idx_hit_code ON scan_hit(code, run_id)",
]


def connect(path=None):
    """打开数据库并建表。WAL 让扫描写入历史时页面仍能读。"""
    db_path = os.path.abspath(path or DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    init_schema(conn)
    return conn


@contextmanager
def open_db(path=None):
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


def init_schema(conn):
    """建齐表和索引。已存在的不动，可以反复调用。"""
    for statement in SCHEMA:
        conn.execute(statement)
    columns = {row[1] for row in conn.execute('PRAGMA table_info(scan_hit)')}
    if 'rule_keys_json' not in columns:
        conn.execute("ALTER TABLE scan_hit ADD COLUMN rule_keys_json TEXT NOT NULL DEFAULT '[]'")
    conn.commit()
