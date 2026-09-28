"""读取本地加密货币 K 线：在读取时完成类型转换和时间换算（库里是 UTC 毫秒，展示用北京时间）。"""
import pandas as pd

from . import db

NUMERIC_FIELDS = ["open", "high", "low", "close", "volume", "quote_asset_volume",
                  "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume"]


def _beijing_text(ms_series):
    """UTC 毫秒批量转北京时间 'YYYY-MM-DD HH:MM:SS'，格式与 A 股分钟线一致，扫描模块可直接复用。"""
    moments = pd.to_datetime(ms_series, unit="ms", utc=True).dt.tz_convert("Asia/Shanghai")
    return moments.dt.strftime("%Y-%m-%d %H:%M:%S")


def load_kline(conn, interval="1h", categories=None, symbols=None, start_ms=None, end_ms=None,
               columns=None):
    """
    读取本地 K 线，返回数值已转换、带北京时间 date 列的 DataFrame，按交易对、时间升序。

    columns 可只取需要的列（至少会带上 symbol 和 open_time），批量分析时能省不少时间。
    """
    categories = list(categories or db.CATEGORIES)
    wanted = list(db.KLINE_COLUMNS) if not columns else \
        list(dict.fromkeys(["symbol", "open_time"] + list(columns)))
    select = ",".join(db.q(c) for c in wanted)
    frames = []
    for category in categories:
        where, params = [], []
        if symbols:
            where.append('"symbol" IN (%s)' % ",".join("?" * len(symbols)))
            params += list(symbols)
        if start_ms is not None:
            where.append('"open_time" >= ?')
            params.append(int(start_ms))
        if end_ms is not None:
            where.append('"open_time" <= ?')
            params.append(int(end_ms))
        sql = f"SELECT {select} FROM {db.kline_table(interval, category)}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        frame = pd.read_sql_query(sql + ' ORDER BY "symbol", "open_time"', conn, params=params)
        if not frame.empty:
            frame.insert(0, "category", category)
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["category", "date"] + wanted)
    result = pd.concat(frames, ignore_index=True)
    for column in NUMERIC_FIELDS:
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    result.insert(1, "date", _beijing_text(result["open_time"]))
    return result.sort_values(["symbol", "open_time"]).reset_index(drop=True)
