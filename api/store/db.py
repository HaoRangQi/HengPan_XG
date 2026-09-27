"""
建库建表和连接管理。

字段原则：K 线、股票、行业、复权因子、交易日历各表的列名和列数，与 Baostock 接口返回的
字段严格一致，一律按字符串原样落库；类型转换、复权、格式化全部放在 reader.py。
只有 board / updated_at 这类本地派生列是例外，建表语句里单独标注。
"""
import os
import sqlite3
from contextlib import contextmanager
from urllib.parse import quote

from ..platform_scanner import BOARD_PREFIXES

# 数据库文件放在 api/data/ 下，和扫描历史同一个目录（.gitignore 已忽略整个目录）
DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "market.db"))

# 第一版只做 60 分钟线。加新周期时在这里登记，建表和同步会自动跟上。
FREQUENCIES = ("60",)

# Baostock 不支持北交所，K 线表只建这四个板块
KLINE_BOARDS = ("sh_main", "sz_main", "sz_gem", "sh_star")
BOARD_LABELS = {
    "sh_main": "沪市主板",
    "sz_main": "深市主板",
    "sz_gem": "创业板",
    "sh_star": "科创板",
}
# 科创板有 50 万开户门槛，默认不同步，由用户在数据管理页自行勾选
DEFAULT_BOARDS = ("sh_main", "sz_main", "sz_gem")

# 分钟线的 10 个字段，顺序与文档一致；查询和写入都用这个顺序
MINUTE_COLUMNS = ("date", "time", "code", "open", "high", "low", "close",
                  "volume", "amount", "adjustflag")


def kline_table(frequency, board):
    """K 线表名，如 kline_60m_sz_gem。"""
    if frequency not in FREQUENCIES:
        raise ValueError(f"unsupported frequency: {frequency}")
    if board not in KLINE_BOARDS:
        raise ValueError(f"unknown board: {board}")
    return f"kline_{frequency}m_{board}"


def board_of(code):
    """按代码前缀判断板块，代码不属于任何已知板块时返回 None。"""
    for board, prefixes in BOARD_PREFIXES.items():
        if code.startswith(tuple(prefixes)):
            return board
    return None


def _kline_ddl(table):
    # 价格列存 TEXT：Baostock 返回的就是字符串，原样存不丢精度、不把空串变成 0。
    # 主键 (code, time) + WITHOUT ROWID 让同一只股票按时间连续存放，
    # 「某只股票最近 N 根」和「某只股票某段日期」都是主键范围扫描。
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
          date       TEXT NOT NULL,
          time       TEXT NOT NULL,
          code       TEXT NOT NULL,
          open       TEXT,
          high       TEXT,
          low        TEXT,
          close      TEXT,
          volume     TEXT,
          amount     TEXT,
          adjustflag TEXT,
          PRIMARY KEY (code, time)
        ) WITHOUT ROWID
    """


SCHEMA = [
    # query_stock_basic()：code, code_name, ipoDate, outDate, type, status
    """CREATE TABLE IF NOT EXISTS stock_basic (
         code       TEXT PRIMARY KEY,
         code_name  TEXT,
         ipoDate    TEXT,
         outDate    TEXT,
         type       TEXT,
         status     TEXT,
         board      TEXT NOT NULL,
         updated_at TEXT
       )""",
    # query_stock_industry()：updateDate, code, code_name, industry, industryClassification
    """CREATE TABLE IF NOT EXISTS stock_industry (
         code                   TEXT PRIMARY KEY,
         code_name              TEXT,
         industry               TEXT,
         industryClassification TEXT,
         updateDate             TEXT
       )""",
    # query_adjust_factor()：code, dividOperateDate, foreAdjustFactor, backAdjustFactor, adjustFactor
    # 三个因子列都存，但读取层只用 backAdjustFactor，原因见 reader.apply_adjust
    """CREATE TABLE IF NOT EXISTS adjust_factor (
         code             TEXT NOT NULL,
         dividOperateDate TEXT NOT NULL,
         foreAdjustFactor TEXT,
         backAdjustFactor TEXT,
         adjustFactor     TEXT,
         PRIMARY KEY (code, dividOperateDate)
       ) WITHOUT ROWID""",
    # query_trade_dates()：calendar_date, is_trading_day
    """CREATE TABLE IF NOT EXISTS trade_calendar (
         calendar_date  TEXT PRIMARY KEY,
         is_trading_day TEXT NOT NULL
       )""",
    # 纯本地表，没有对应接口
    """CREATE TABLE IF NOT EXISTS sync_log (
         id          INTEGER PRIMARY KEY AUTOINCREMENT,
         action      TEXT,
         boards      TEXT,
         started_at  TEXT,
         finished_at TEXT,
         status      TEXT,
         requests    INTEGER DEFAULT 0,
         rows        INTEGER DEFAULT 0,
         failed      INTEGER DEFAULT 0,
         message     TEXT
       )""",
    """CREATE TABLE IF NOT EXISTS store_meta (
         key   TEXT PRIMARY KEY,
         value TEXT
       )""",
    # 首次完整复权因子按证券断点续传；无除权记录的证券也必须留下完成标记。
    """CREATE TABLE IF NOT EXISTS adjust_factor_sync (
         code         TEXT PRIMARY KEY,
         completed_at TEXT NOT NULL
       )""",
]


def connect(path=None):
    """打开数据库并建表。WAL 让同步写入时扫描仍能读。"""
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


@contextmanager
def open_readonly_db(path=None):
    """打开不会建表或改 PRAGMA 持久状态的只读连接，供扫描子进程使用。"""
    db_path = os.path.abspath(path or DB_PATH)
    uri = f"file:{quote(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


def init_schema(conn):
    """建齐所有表。已存在的表不动，可以反复调用。"""
    for statement in SCHEMA:
        conn.execute(statement)
    for frequency in FREQUENCIES:
        for board in KLINE_BOARDS:
            conn.execute(_kline_ddl(kline_table(frequency, board)))
    for frequency in FREQUENCIES:
        _create_union_view(conn, frequency)
    conn.commit()


def _create_union_view(conn, frequency):
    """跨板块视图，多一列 board，供扫全市场用。"""
    view = f"kline_{frequency}m_all"
    parts = [f"SELECT '{board}' AS board, * FROM {kline_table(frequency, board)}"
             for board in KLINE_BOARDS]
    conn.execute(f"CREATE VIEW IF NOT EXISTS {view} AS " + " UNION ALL ".join(parts))


def upsert(conn, table, columns, rows):
    """按主键覆盖写入。重复同步只会更新，不会产生重复行。"""
    if not rows:
        return 0
    placeholders = ",".join("?" * len(columns))
    names = ",".join(columns)
    conn.executemany(
        f"INSERT INTO {table} ({names}) VALUES ({placeholders}) "
        f"ON CONFLICT DO UPDATE SET " +
        ",".join(f"{c}=excluded.{c}" for c in columns),
        rows)
    return len(rows)


def latest_time(conn, frequency, board, code):
    """某只股票本地最后一根 K 线的 time，没有数据返回 None。走主键，0 毫秒级。"""
    row = conn.execute(
        f"SELECT MAX(time) FROM {kline_table(frequency, board)} WHERE code=?",
        (code,)).fetchone()
    return row[0] if row else None

def latest_times(conn, frequency, board):
    """整个板块每只股票的最后一根 time，用于批量计算增量起点。"""
    rows = conn.execute(
        f"SELECT code, MAX(time) FROM {kline_table(frequency, board)} GROUP BY code")
    return {code: value for code, value in rows}


def latest_date(conn, frequency="60", boards=None):
    """所选板块本地行情的最新日期。"""
    boards = list(boards or KLINE_BOARDS)
    values = []
    for board in boards:
        table = kline_table(frequency, board)
        value = conn.execute(f"SELECT MAX(date) FROM {table}").fetchone()[0]
        if value:
            values.append(value)
    return max(values) if values else None


def has_kline_date(conn, date, frequency="60", boards=None):
    """所选板块是否至少有一根指定交易日行情。"""
    for board in list(boards or KLINE_BOARDS):
        row = conn.execute(
            f"SELECT 1 FROM {kline_table(frequency, board)} WHERE date=? LIMIT 1", (date,)).fetchone()
        if row:
            return True
    return False


def stock_list(conn, boards=None, include_delisted=False):
    """股票池：stock_basic 关联 stock_industry，返回扫描用的字典列表。"""
    sql = ("SELECT b.code, b.code_name, b.board, b.status, i.industry "
           "FROM stock_basic b LEFT JOIN stock_industry i ON i.code = b.code")
    where, params = [], []
    if boards:
        where.append("b.board IN (%s)" % ",".join("?" * len(boards)))
        params += list(boards)
    if not include_delisted:
        where.append("b.status = '1'")
    if where:
        sql += " WHERE " + " AND ".join(where)
    return [{"code": r["code"], "name": r["code_name"], "board": r["board"],
             "industry": r["industry"] or "未知行业"}
            for r in conn.execute(sql + " ORDER BY b.code", params)]


def stock_list_with_kline(conn, frequency="60", boards=None):
    """只返回本地已有行情的上市股票，避免扫描空壳股票池。"""
    boards = list(boards or DEFAULT_BOARDS)
    available = set()
    for board in boards:
        table = kline_table(frequency, board)
        available.update(row[0] for row in conn.execute(f"SELECT DISTINCT code FROM {table}"))
    return [stock for stock in stock_list(conn, boards) if stock["code"] in available]


def stock_inventory(conn, boards=None, frequency="60", keyword=None, having="all",
                    include_delisted=False):
    """
    股票清单，每只带上本地行情的根数和起止日期，数据管理页左侧列表用。

    一个板块 1700 只、全量查询约 50 毫秒，不分页；前端拿到后本地搜索、本地筛选。

    keyword：按代码或名称模糊匹配
    having：all 全部 / with 只看有行情的 / without 只看缺行情的
    """
    boards = list(boards or KLINE_BOARDS)
    unknown = set(boards) - set(KLINE_BOARDS)
    if unknown:
        raise ValueError(f"unknown boards: {', '.join(sorted(unknown))}")
    if having not in ("all", "with", "without"):
        raise ValueError("having must be 'all', 'with', or 'without'")

    result = []
    for board in boards:
        table = kline_table(frequency, board)
        # 子查询先把该板块的行情聚成「每只一行」，再和股票池左连接。
        # 板块表已按 code 物理有序，GROUP BY code 走主键顺序扫描，不需要额外索引。
        sql = (f"SELECT b.code, b.code_name, b.status, i.industry, "
               f"       COALESCE(k.bars, 0) AS bars, k.first_date, k.last_date "
               f"FROM stock_basic b "
               f"LEFT JOIN stock_industry i ON i.code = b.code "
               f"LEFT JOIN (SELECT code, COUNT(*) AS bars, MIN(date) AS first_date, "
               f"                  MAX(date) AS last_date FROM {table} GROUP BY code) k "
               f"       ON k.code = b.code "
               f"WHERE b.board = ?")
        params = [board]
        if not include_delisted:
            sql += " AND b.status = '1'"
        if keyword:
            sql += " AND (b.code LIKE ? OR b.code_name LIKE ?)"
            like = f"%{keyword}%"
            params += [like, like]
        if having == "with":
            # 不能写 bars > 0：WHERE 里的 bars 解析成子查询列 k.bars，
            # 没有行情的股票那里是 NULL，比较结果也是 NULL（不成立）。
            sql += " AND COALESCE(k.bars, 0) > 0"
        elif having == "without":
            sql += " AND COALESCE(k.bars, 0) = 0"
        result += [{"code": r["code"], "name": r["code_name"], "board": board,
                    "industry": r["industry"] or "未知行业", "status": r["status"],
                    "bars": r["bars"], "first_date": r["first_date"],
                    "last_date": r["last_date"]}
                   for r in conn.execute(sql + " ORDER BY b.code", params)]
    return result


def kline_range(conn, code, frequency="60", start=None, end=None):
    """某只股票在指定日期区间内的本地行情根数和起止，查询前先给个底。"""
    board = board_of(code)
    if board not in KLINE_BOARDS:
        return {"bars": 0, "first_date": None, "last_date": None}
    where, params = ["code = ?"], [code]
    if start:
        where.append("date >= ?")
        params.append(start)
    if end:
        where.append("date <= ?")
        params.append(end)
    row = conn.execute(
        f"SELECT COUNT(*) bars, MIN(date) first_date, MAX(date) last_date "
        f"FROM {kline_table(frequency, board)} WHERE " + " AND ".join(where), params).fetchone()
    return {"bars": row["bars"], "first_date": row["first_date"], "last_date": row["last_date"]}


def trading_days(conn, start=None, end=None):
    """交易日列表（升序）。"""
    sql = "SELECT calendar_date FROM trade_calendar WHERE is_trading_day='1'"
    params = []
    if start:
        sql += " AND calendar_date >= ?"
        params.append(start)
    if end:
        sql += " AND calendar_date <= ?"
        params.append(end)
    return [r[0] for r in conn.execute(sql + " ORDER BY calendar_date", params)]


def board_stats(conn, frequency, board):
    """单个板块的行数、股票数、起止时间，数据管理页概览用。"""
    row = conn.execute(
        f"SELECT COUNT(*) n, COUNT(DISTINCT code) codes, MIN(date) first, MAX(date) last "
        f"FROM {kline_table(frequency, board)}").fetchone()
    return {"board": board, "label": BOARD_LABELS[board], "rows": row["n"],
            "codes": row["codes"], "first_date": row["first"], "last_date": row["last"]}


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM store_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO store_meta (key,value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit()
