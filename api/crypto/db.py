"""
建库建表和连接管理。

字段原则和 A 股一样：各表的列名、列数与 Binance 接口返回严格对应，原样落库，
类型转换和时间换算全部放在 reader.py。K 线接口返回的是 12 个元素的数组、没有字段名，
列名按官方文档对每个下标的说明取名（Open time → open_time），顺序与下标一致。

本地派生列（category / symbol / raw / updated_at）在建表语句里单独标注。
"""
import os
import sqlite3
from contextlib import contextmanager

# 独立的库文件，不和 A 股的 market.db 混在一起
DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "crypto.db"))

# 第一版只做 1 小时线。加新周期时在这里登记（毫秒数用于截断未走完的 K 线）
INTERVALS = {"1h": 3_600_000}

# 两类永续按 contractType 分表：波动差约 4 倍，分析时必须分开看（研究文档第 6 节）
CATEGORIES = ("perpetual", "tradifi")
CATEGORY_LABELS = {"perpetual": "加密永续", "tradifi": "TradFi 永续"}
CONTRACT_CATEGORY = {"PERPETUAL": "perpetual", "TRADIFI_PERPETUAL": "tradifi"}

# K 线数组的 12 个下标，按官方文档命名；前面加一列本地的 symbol
KLINE_FIELDS = (
    "open_time",                     # [0]  Open time，毫秒，UTC
    "open",                          # [1]  Open
    "high",                          # [2]  High
    "low",                           # [3]  Low
    "close",                         # [4]  Close
    "volume",                        # [5]  Volume，单位是币
    "close_time",                    # [6]  Close time，毫秒
    "quote_asset_volume",            # [7]  Quote asset volume，单位 USDT
    "number_of_trades",              # [8]  Number of trades
    "taker_buy_base_asset_volume",   # [9]  Taker buy base asset volume
    "taker_buy_quote_asset_volume",  # [10] Taker buy quote asset volume
    "ignore",                        # [11] Ignore，保留字段
)
KLINE_COLUMNS = ("symbol",) + KLINE_FIELDS

# exchangeInfo.symbols 里的字段。数组字段存 JSON 文本；整条原始 JSON 另存一份 raw，
# 接口以后新增字段也不会丢
SYMBOL_FIELDS = (
    "symbol", "pair", "contractType", "deliveryDate", "onboardDate", "status",
    "maintMarginPercent", "requiredMarginPercent", "baseAsset", "quoteAsset", "marginAsset",
    "pricePrecision", "quantityPrecision", "baseAssetPrecision", "quotePrecision",
    "underlyingType", "underlyingSubType", "settlePlan", "triggerProtect",
    "liquidationFee", "marketTakeBound", "filters", "orderTypes", "timeInForce",
)
SYMBOL_JSON_FIELDS = ("underlyingSubType", "filters", "orderTypes", "timeInForce")
SYMBOL_COLUMNS = SYMBOL_FIELDS + ("raw", "category", "updated_at")

# ticker/24hr 的 16 个字段，顺序与接口返回一致
TICKER_FIELDS = (
    "symbol", "priceChange", "priceChangePercent", "weightedAvgPrice", "lastPrice", "lastQty",
    "openPrice", "highPrice", "lowPrice", "volume", "quoteVolume",
    "openTime", "closeTime", "firstId", "lastId", "count",
)
TICKER_COLUMNS = TICKER_FIELDS + ("updated_at",)


def kline_table(interval, category):
    """K 线表名，如 crypto_kline_1h_perpetual。"""
    if interval not in INTERVALS:
        raise ValueError(f"unsupported interval: {interval}")
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category}")
    return f"crypto_kline_{interval}_{category}"


def q(name):
    """列名加双引号。K 线的 ignore 列和 SQLite 关键字同名，统一加引号最省心。"""
    return f'"{name}"'


def _kline_ddl(table):
    # 价格、成交量接口返回的是字符串，原样存 TEXT；时间和笔数是整数，存 INTEGER。
    # 主键 (symbol, open_time) + WITHOUT ROWID：同一交易对按时间连续存放，
    # 单个交易对取最近 N 根、取某段时间都是主键范围扫描，不需要额外索引。
    return f"""
        CREATE TABLE IF NOT EXISTS {table} (
          "symbol"                       TEXT    NOT NULL,  -- 本地：K 线接口不返回交易对，按请求参数补上
          "open_time"                    INTEGER NOT NULL,
          "open"                         TEXT,
          "high"                         TEXT,
          "low"                          TEXT,
          "close"                        TEXT,
          "volume"                       TEXT,
          "close_time"                   INTEGER,
          "quote_asset_volume"           TEXT,
          "number_of_trades"             INTEGER,
          "taker_buy_base_asset_volume"  TEXT,
          "taker_buy_quote_asset_volume" TEXT,
          "ignore"                       TEXT,
          PRIMARY KEY ("symbol", "open_time")
        ) WITHOUT ROWID
    """


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS crypto_symbol (
         "symbol"                TEXT PRIMARY KEY,
         "pair"                  TEXT,
         "contractType"          TEXT,
         "deliveryDate"          INTEGER,
         "onboardDate"           INTEGER,
         "status"                TEXT,
         "maintMarginPercent"    TEXT,
         "requiredMarginPercent" TEXT,
         "baseAsset"             TEXT,
         "quoteAsset"            TEXT,
         "marginAsset"           TEXT,
         "pricePrecision"        INTEGER,
         "quantityPrecision"     INTEGER,
         "baseAssetPrecision"    INTEGER,
         "quotePrecision"        INTEGER,
         "underlyingType"        TEXT,
         "underlyingSubType"     TEXT,     -- JSON 数组
         "settlePlan"            INTEGER,
         "triggerProtect"        TEXT,
         "liquidationFee"        TEXT,
         "marketTakeBound"       TEXT,
         "filters"               TEXT,     -- JSON 数组
         "orderTypes"            TEXT,     -- JSON 数组
         "timeInForce"           TEXT,     -- JSON 数组
         "raw"                   TEXT,     -- 本地：整条原始 JSON
         "category"              TEXT,     -- 本地：perpetual / tradifi
         "updated_at"            TEXT      -- 本地：最后同步时间
       )""",
    """CREATE TABLE IF NOT EXISTS crypto_ticker_24hr (
         "symbol"             TEXT PRIMARY KEY,
         "priceChange"        TEXT,
         "priceChangePercent" TEXT,
         "weightedAvgPrice"   TEXT,
         "lastPrice"          TEXT,
         "lastQty"            TEXT,
         "openPrice"          TEXT,
         "highPrice"          TEXT,
         "lowPrice"           TEXT,
         "volume"             TEXT,
         "quoteVolume"        TEXT,
         "openTime"           INTEGER,
         "closeTime"          INTEGER,
         "firstId"            INTEGER,
         "lastId"             INTEGER,
         "count"              INTEGER,
         "updated_at"         TEXT       -- 本地：拉取时间
       )""",
    # 纯本地表，结构与 A 股库的 sync_log 相同
    """CREATE TABLE IF NOT EXISTS sync_log (
         id          INTEGER PRIMARY KEY AUTOINCREMENT,
         action      TEXT,
         boards      TEXT,      -- 这里存的是 category，沿用 A 股库的列名方便复用前端
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
]


def connect(path=None):
    """打开数据库并建表。WAL 让同步写入时查询仍能读。"""
    db_path = os.path.abspath(path or DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
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
    """建齐所有表，已存在的不动，可以反复调用。"""
    for statement in SCHEMA:
        conn.execute(statement)
    for interval in INTERVALS:
        for category in CATEGORIES:
            conn.execute(_kline_ddl(kline_table(interval, category)))
        _create_union_view(conn, interval)
    conn.commit()


def _create_union_view(conn, interval):
    """跨类别视图，多一列 category。"""
    view = f"crypto_kline_{interval}_all"
    parts = [f"SELECT '{category}' AS category, * FROM {kline_table(interval, category)}"
             for category in CATEGORIES]
    conn.execute(f"DROP VIEW IF EXISTS {view}")
    conn.execute(f"CREATE VIEW {view} AS " + " UNION ALL ".join(parts))


def upsert(conn, table, columns, rows):
    """按主键覆盖写入。重复同步只会更新，不会产生重复行。"""
    if not rows:
        return 0
    names = ",".join(q(c) for c in columns)
    placeholders = ",".join("?" * len(columns))
    updates = ",".join(f"{q(c)}=excluded.{q(c)}" for c in columns)
    conn.executemany(
        f"INSERT INTO {table} ({names}) VALUES ({placeholders}) "
        f"ON CONFLICT DO UPDATE SET {updates}", rows)
    return len(rows)


def latest_open_times(conn, interval, category):
    """每个交易对本地最后一根 K 线的 open_time，用于算增量起点。"""
    rows = conn.execute(
        f'SELECT "symbol", MAX("open_time") FROM {kline_table(interval, category)} GROUP BY "symbol"')
    return {symbol: value for symbol, value in rows}


def symbol_pool(conn, categories=None, min_quote_volume=0, symbols=None, include_inactive=False):
    """
    币池：两类永续、USDT 计价、正在交易。

    只按 symbol 以 USDT 结尾过滤会混进正在下架结算（SETTLING）的合约，
    它们仍出现在 ticker 里但 K 线已停止更新（研究文档第 4 节）。
    """
    categories = list(categories or CATEGORIES)
    sql = ('SELECT s."symbol", s."category", s."contractType", s."status", s."baseAsset", '
           's."onboardDate", t."quoteVolume", t."lastPrice", t."priceChangePercent" '
           'FROM crypto_symbol s LEFT JOIN crypto_ticker_24hr t ON t."symbol" = s."symbol" '
           'WHERE s."category" IN (%s)' % ",".join("?" * len(categories)))
    params = list(categories)
    if not include_inactive:
        sql += " AND s.\"status\" = 'TRADING'"
    if symbols:
        sql += ' AND s."symbol" IN (%s)' % ",".join("?" * len(symbols))
        params += list(symbols)
    rows = conn.execute(sql + ' ORDER BY s."symbol"', params).fetchall()
    pool = []
    for r in rows:
        quote_volume = float(r["quoteVolume"]) if r["quoteVolume"] not in (None, "") else 0.0
        if quote_volume < (min_quote_volume or 0):
            continue
        pool.append({"symbol": r["symbol"], "category": r["category"],
                     "contractType": r["contractType"], "status": r["status"],
                     "baseAsset": r["baseAsset"], "onboardDate": r["onboardDate"],
                     "quoteVolume": quote_volume,
                     "lastPrice": r["lastPrice"], "priceChangePercent": r["priceChangePercent"]})
    return pool


def symbol_inventory(conn, categories=None, interval="1h", having="all", include_inactive=False):
    """
    交易对清单，每个带上本地 K 线根数和起止时间，数据管理页左侧列表用。

    一个类别几百个交易对，全量查询很快，不分页；前端拿到后本地搜索、筛选、排序。
    """
    categories = list(categories or CATEGORIES)
    if set(categories) - set(CATEGORIES):
        raise ValueError(f"unknown categories: {sorted(set(categories) - set(CATEGORIES))}")
    if having not in ("all", "with", "without"):
        raise ValueError("having must be 'all', 'with', or 'without'")
    result = []
    for category in categories:
        table = kline_table(interval, category)
        # WHERE 里必须写完整的 COALESCE 表达式：直接写别名 bars 会被解析成子查询列 k.bars，
        # 没有 K 线的交易对那里是 NULL，比较永远不成立
        sql = ('SELECT s."symbol", s."status", s."baseAsset", s."onboardDate", '
               't."quoteVolume", t."lastPrice", t."priceChangePercent", '
               'COALESCE(k.bars, 0) AS bars, k.first_time, k.last_time '
               'FROM crypto_symbol s '
               'LEFT JOIN crypto_ticker_24hr t ON t."symbol" = s."symbol" '
               f'LEFT JOIN (SELECT "symbol", COUNT(*) AS bars, MIN("open_time") AS first_time, '
               f'                  MAX("open_time") AS last_time FROM {table} GROUP BY "symbol") k '
               '       ON k."symbol" = s."symbol" '
               'WHERE s."category" = ?')
        params = [category]
        if not include_inactive:
            sql += " AND s.\"status\" = 'TRADING'"
        if having == "with":
            sql += " AND COALESCE(k.bars, 0) > 0"
        elif having == "without":
            sql += " AND COALESCE(k.bars, 0) = 0"
        for r in conn.execute(sql + ' ORDER BY s."symbol"', params):
            result.append({
                "symbol": r["symbol"], "category": category, "status": r["status"],
                "baseAsset": r["baseAsset"], "onboardDate": r["onboardDate"],
                "quoteVolume": float(r["quoteVolume"]) if r["quoteVolume"] not in (None, "") else None,
                "lastPrice": r["lastPrice"], "priceChangePercent": r["priceChangePercent"],
                "bars": r["bars"], "first_time": r["first_time"], "last_time": r["last_time"],
            })
    return result


def category_stats(conn, interval, category):
    """单个类别的行数、交易对数、起止时间，概览用。"""
    row = conn.execute(
        f'SELECT COUNT(*) n, COUNT(DISTINCT "symbol") symbols, MIN("open_time") first, '
        f'MAX("open_time") last FROM {kline_table(interval, category)}').fetchone()
    pool = conn.execute(
        "SELECT COUNT(*) FROM crypto_symbol WHERE \"category\"=? AND \"status\"='TRADING'",
        (category,)).fetchone()[0]
    return {"category": category, "label": CATEGORY_LABELS[category], "rows": row["n"],
            "symbols": row["symbols"], "pool_symbols": pool,
            "first_time": row["first"], "last_time": row["last"]}


def category_of(conn, symbol):
    """查交易对属于哪个类别；本地没有这个交易对时返回 None。"""
    row = conn.execute('SELECT "category" FROM crypto_symbol WHERE "symbol"=?', (symbol,)).fetchone()
    return row[0] if row else None


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM store_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO store_meta (key,value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
