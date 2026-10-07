"""读取本地 60 分钟 K 线，并在读取时完成类型、时间和复权处理。"""
from datetime import datetime

import pandas as pd

from ..hengpan.fetcher import _normalise_minute_time
from . import db


OUTPUT_COLUMNS = [
    "date", "time", "code", "open", "high", "low", "close", "volume", "amount",
    "adjustflag", "turn", "tradestatus", "isST",
]
PRICE_COLUMNS = ["open", "high", "low", "close"]


def _empty_frame():
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _load_raw(conn, board, start, end, codes):
    table = db.kline_table("60", board)
    where = []
    params = []
    if start:
        where.append("date >= ?")
        params.append(start)
    if end:
        where.append("date <= ?")
        params.append(end)
    if codes:
        where.append("code IN (%s)" % ",".join("?" * len(codes)))
        params.extend(codes)
    sql = f"SELECT date,time,code,open,high,low,close,volume,amount,adjustflag FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY code,time"
    return pd.read_sql_query(sql, conn, params=params)


def _apply_adjustment(conn, frame, adjust):
    if adjust == "raw" or frame.empty:
        return frame
    if adjust not in ("qfq", "hfq"):
        raise ValueError("adjust must be 'qfq', 'hfq', or 'raw'")

    codes = frame["code"].drop_duplicates().tolist()
    placeholders = ",".join("?" * len(codes))
    factors = pd.read_sql_query(
        f"SELECT code, dividOperateDate, backAdjustFactor FROM adjust_factor "
        f"WHERE code IN ({placeholders}) ORDER BY code, dividOperateDate",
        conn, params=codes)
    if factors.empty:
        return frame
    factors["factor"] = pd.to_numeric(factors["backAdjustFactor"], errors="coerce")
    factors["date"] = pd.to_datetime(factors["dividOperateDate"], errors="coerce")
    factors = factors.dropna(subset=["date", "factor"])[["code", "date", "factor"]]
    if factors.empty:
        return frame

    result = frame.copy()
    result["_date"] = pd.to_datetime(result["date"].str[:10], errors="coerce")
    result = pd.merge_asof(
        result.sort_values(["_date", "code"]),
        factors.sort_values(["date", "code"]),
        left_on="_date", right_on="date", by="code", direction="backward",
    )
    if "date_x" in result:
        result = result.rename(columns={"date_x": "date"})
    result["factor"] = result["factor"].fillna(1.0)
    if adjust == "qfq":
        latest = factors.groupby("code")["factor"].last().rename("latest_factor")
        result = result.join(latest, on="code")
        result["factor"] = result["factor"] / result["latest_factor"].replace(0, 1)
    for column in PRICE_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce") * result["factor"]
    return result.drop(columns=["_date", "date_y", "latest_factor", "factor"], errors="ignore")


def _format_times(frame):
    """
    把 time 字段（YYYYMMDDHHMMSSsss）批量格式化成 'YYYY-MM-DD HH:MM:SS'。

    逐行调 _normalise_minute_time 在 13 万行上要 0.7 秒，向量化字符串切片只要 0.1 秒，
    两者结果逐行一致。少数长度不足 14 位的异常值回退到逐行解析。
    """
    text = frame["time"].astype(str)
    formatted = (text.str[0:4] + "-" + text.str[4:6] + "-" + text.str[6:8] + " "
                 + text.str[8:10] + ":" + text.str[10:12] + ":" + text.str[12:14])
    malformed = ~text.str.fullmatch(r"\d{14}\d*")
    if malformed.any():
        formatted[malformed] = [
            _normalise_minute_time(day, value)
            for day, value in zip(frame.loc[malformed, "date"], frame.loc[malformed, "time"])
        ]
    return formatted


def load_kline_60m(conn, boards=None, start=None, end=None, adjust="qfq", codes=None):
    """读取本地 60 分钟线，输出与现有扫描器相容的清洗后 DataFrame。"""
    boards = list(boards or db.DEFAULT_BOARDS)
    unknown = set(boards) - set(db.KLINE_BOARDS)
    if unknown:
        raise ValueError(f"unknown boards: {', '.join(sorted(unknown))}")
    if adjust not in ("qfq", "hfq", "raw"):
        raise ValueError("adjust must be 'qfq', 'hfq', or 'raw'")
    selected = None if codes is None else set(codes)
    if selected == set():
        return _empty_frame()
    frames = []
    for board in boards:
        board_codes = [code for code in selected if db.board_of(code) == board] if selected is not None else None
        if selected is not None and not board_codes:
            continue
        raw = _load_raw(conn, board, start, end, board_codes)
        if not raw.empty:
            frames.append(raw)
    if not frames:
        return _empty_frame()
    result = pd.concat(frames, ignore_index=True)
    result["date"] = _format_times(result)
    result["time"] = result["date"]
    result = _apply_adjustment(conn, result, adjust)
    for column in PRICE_COLUMNS + ["volume", "amount"]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["turn"] = float("nan")
    result["tradestatus"] = "1"
    result["isST"] = None
    # Older databases remain readable without a migration or network request.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stock_daily_status'").fetchone():
        codes_in_frame = result["code"].drop_duplicates().tolist()
        marks = ",".join("?" * len(codes_in_frame))
        statuses = {(row[0], row[1]): row[2] for row in conn.execute(
            f"SELECT code,date,isST FROM stock_daily_status WHERE code IN ({marks}) AND date BETWEEN ? AND ?",
            [*codes_in_frame, result["date"].str[:10].min(), result["date"].str[:10].max()])}
        result["isST"] = [statuses.get((code, day)) for code, day in
                          zip(result["code"], result["date"].str[:10])]
    return result[OUTPUT_COLUMNS].sort_values(["code", "date"]).reset_index(drop=True)


def latest_date(conn, boards=None, codes=None):
    """返回所选本地 K 线的最新交易日。"""
    boards = list(boards or db.DEFAULT_BOARDS)
    selected = None if codes is None else set(codes)
    if selected == set():
        return None
    dates = []
    for board in boards:
        board_codes = [code for code in selected if db.board_of(code) == board] if selected is not None else None
        if selected is not None and not board_codes:
            continue
        table = db.kline_table("60", board)
        where, params = [], []
        if board_codes:
            where.append("code IN (%s)" % ",".join("?" * len(board_codes)))
            params.extend(board_codes)
        sql = f"SELECT MAX(date) FROM {table}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        value = conn.execute(sql, params).fetchone()[0]
        if value:
            dates.append(value)
    return max(dates) if dates else None


def load_one_kline_60m(db_path, code, start, end, adjust="qfq"):
    with db.open_readonly_db(db_path) as conn:
        board = db.board_of(code)
        if board not in db.KLINE_BOARDS:
            return _empty_frame()
        return load_kline_60m(conn, [board], start=start, end=end, adjust=adjust, codes=[code])


def latest_timestamp(conn, boards=None, codes=None, end=None):
    """Latest closed local bar in the selected universe, resolved once per scan."""
    from ..data_quality import closed_frame
    selected = None if codes is None else set(codes)
    if selected == set():
        return None
    values = []
    for board in boards or db.DEFAULT_BOARDS:
        board_codes = [code for code in selected if db.board_of(code) == board] if selected is not None else None
        if selected is not None and not board_codes:
            continue
        where, params = [], []
        if board_codes:
            where.append("code IN (%s)" % ",".join("?" * len(board_codes)))
            params.extend(board_codes)
        if end:
            where.append("date <= ?")
            params.append(str(end)[:10])
        sql = f"SELECT DISTINCT date,time FROM {db.kline_table('60', board)}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY time DESC LIMIT 8"
        frame = pd.read_sql_query(sql, conn, params=params)
        if not frame.empty:
            frame["date"] = _format_times(frame)
            frame = closed_frame(frame.sort_values("date"), "60")
            if not frame.empty:
                values.append(frame["date"].max())
    return max(values) if values else None
