"""
横盘选股的 K 线取数。
和首页的 fetch_kline_data 相比，字段多了 amount、tradestatus、isST，并且会删掉停牌行；
登录和重连复用 api/data_fetcher.py 的 baostock_login / baostock_relogin。
"""
import time
from datetime import datetime, timedelta

import baostock as bs
import pandas as pd
from colorama import Fore, Style

from ..data_fetcher import BaostockBlacklisted, is_blacklist_error, baostock_login, baostock_relogin

DAILY_FIELDS = "date,open,high,low,close,volume,amount,turn,tradestatus,isST"
MINUTE_FIELDS = "date,time,open,high,low,close,volume,amount"
# Kept as a public alias for callers that imported the old daily constant.
KLINE_FIELDS = DAILY_FIELDS
NUMERIC_COLUMNS = ["open", "high", "low", "close", "volume", "amount", "turn"]
INDEX_CODE = "sh.000001"  # 扫描日取上证指数最新一根日线的日期
MINUTE_PROBE_LIMIT = 8


def _validate_frequency(frequency):
    if frequency not in ("d", "60"):
        raise ValueError("frequency must be 'd' or '60'")
    return frequency


def _fields_for_frequency(frequency):
    return DAILY_FIELDS if _validate_frequency(frequency) == "d" else MINUTE_FIELDS


def query_kline(code, fields, start_date, end_date, frequency="d", adjustflag="2",
                retry_attempts=2, retry_delay=1):
    """查询一只证券的原始 K 线，失败时重新登录再试。"""
    _validate_frequency(frequency)
    last_error = ""
    for attempt in range(1, retry_attempts + 1):
        try:
            baostock_login()
            rs = bs.query_history_k_data_plus(code, fields, start_date=start_date, end_date=end_date,
                                              frequency=frequency, adjustflag=adjustflag)
            rows = []
            while rs.error_code == '0' and rs.next():
                rows.append(rs.get_row_data())
            if rs.error_code == '0':
                columns = list(getattr(rs, "fields", None) or fields.split(","))
                return pd.DataFrame(rows, columns=columns)
            last_error = rs.error_msg
        except BaostockBlacklisted:
            raise            # 黑名单：重试只会加重封禁，直接上抛让整轮扫描中止
        except Exception as e:
            last_error = str(e)

        label = "日线" if frequency == "d" else "60分钟线"
        if is_blacklist_error(last_error):
            raise BaostockBlacklisted(f"{code} {label}获取失败：{last_error}")
        print(f"{Fore.YELLOW}Attempt {attempt}/{retry_attempts}: {label} query failed for {code}: "
              f"{last_error}{Style.RESET_ALL}")
        if attempt < retry_attempts:
            time.sleep(retry_delay * (1 + attempt * 0.5))
            baostock_relogin()

    label = "日线" if frequency == "d" else "60分钟线"
    raise ConnectionError(f"{code} {label}获取失败：{last_error}")


def query_daily(code, fields, start_date, end_date, adjustflag="2",
                retry_attempts=2, retry_delay=1):
    """兼容旧调用的日线原始查询。"""
    return query_kline(code, fields, start_date, end_date, frequency="d", adjustflag=adjustflag,
                       retry_attempts=retry_attempts, retry_delay=retry_delay)


def _normalise_minute_time(date_value, time_value):
    """把 Baostock 的 time 字段统一为 YYYY-MM-DD HH:MM:SS。"""
    raw_time = "" if time_value is None else str(time_value).strip()
    if raw_time.endswith(".0"):
        raw_time = raw_time[:-2]
    parsed = None
    if raw_time.isdigit():
        if len(raw_time) >= 14:
            # Baostock commonly returns YYYYMMDDHHMMSSmmm.
            try:
                parsed = datetime.strptime(raw_time[:14], "%Y%m%d%H%M%S")
            except ValueError:
                parsed = None
        elif len(raw_time) >= 13:
            try:
                parsed = datetime.fromtimestamp(int(raw_time[:13]) / 1000)
            except (ValueError, OverflowError, OSError):
                parsed = None
    if parsed is None and raw_time:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%H:%M:%S", "%H:%M"):
            try:
                value = datetime.strptime(raw_time, fmt)
                if fmt.startswith("%H"):
                    date_text = str(date_value)[:10]
                    parsed = datetime.strptime(date_text, "%Y-%m-%d").replace(
                        hour=value.hour, minute=value.minute, second=value.second)
                else:
                    parsed = value
                break
            except ValueError:
                continue
    if parsed is None:
        date_text = str(date_value)[:10]
        try:
            parsed = datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError:
            return str(date_value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def clean_kline(df, frequency="d"):
    """规范数值和时间字段，删掉停牌行和价格缺失行。"""
    _validate_frequency(frequency)
    if df.empty:
        return df
    df = df.copy()
    if "date" not in df:
        return pd.DataFrame()
    if frequency == "60":
        if "time" in df:
            df["date"] = [_normalise_minute_time(day, value)
                           for day, value in zip(df["date"], df["time"])]
        else:
            df["date"] = [_normalise_minute_time(value, None) for value in df["date"]]
    if "tradestatus" not in df:
        df["tradestatus"] = "1"
    if "isST" not in df:
        df["isST"] = "0"
    trade_status = pd.to_numeric(df["tradestatus"], errors="coerce")
    df["isST"] = df["isST"].astype(str)
    for column in NUMERIC_COLUMNS:
        if column not in df:
            df[column] = float("nan")
        df[column] = pd.to_numeric(df[column], errors="coerce").astype(float)
    df = df[trade_status.eq(1)].dropna(subset=["open", "high", "low", "close"])
    return df.sort_values("date").reset_index(drop=True)


def fetch_kline(code, start_date, end_date, frequency="d", retry_attempts=2):
    """在扫描子进程里运行：拉取前复权 K 线并按时间升序返回。"""
    if frequency == "d":
        # Keep the legacy daily hook available for callers/tests that replace
        # fetch_daily_kline while using the new generic entry point.
        return fetch_daily_kline(code, start_date, end_date, retry_attempts=retry_attempts)
    fields = _fields_for_frequency(frequency)
    return clean_kline(query_kline(code, fields, start_date, end_date, frequency=frequency,
                                   retry_attempts=retry_attempts), frequency=frequency)


def fetch_daily_kline(code, start_date, end_date, retry_attempts=2):
    """兼容旧调用的日线取数包装。"""
    return clean_kline(query_daily(code, DAILY_FIELDS, start_date, end_date,
                                   retry_attempts=retry_attempts), frequency="d")


def resolve_scan_date(requested=None, frequency="d", probe_codes=None):
    """
    确定扫描日：日线用上证指数交易日；60 分钟线用所选板块的实际股票抽样。

    Baostock 的指数分钟线查询可能成功但返回空数据，不能用它判断股票分钟数据是否可用。
    """
    _validate_frequency(frequency)
    end = requested or datetime.now().strftime("%Y-%m-%d")
    start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")

    if frequency == "d":
        data = query_daily(INDEX_CODE, "date", start, end, adjustflag="3", retry_attempts=3)
        dates = data["date"].astype(str).str[:10] if not data.empty else pd.Series(dtype=str)
        source_label = "上证指数日线"
    else:
        codes = list(dict.fromkeys(probe_codes or []))[:MINUTE_PROBE_LIMIT]
        if not codes:
            raise ValueError("60分钟扫描需要从所选板块的股票池确定最新数据日期")
        date_parts = []
        errors = []
        for code in codes:
            try:
                data = query_kline(code, "date,time", start, end, frequency="60",
                                   adjustflag="2", retry_attempts=3)
            except Exception as error:
                errors.append(f"{code}: {error}")
                continue
            if not data.empty:
                date_parts.append(data["date"].astype(str).str[:10])
        if not date_parts and errors:
            raise ConnectionError("所选板块的分钟线样本全部查询失败：" + "; ".join(errors))
        dates = pd.concat(date_parts, ignore_index=True) if date_parts else pd.Series(dtype=str)
        source_label = "所选板块样本股票的60分钟线"

    if dates.empty:
        raise ValueError(f"{start} 至 {end} 之间没有{source_label}，无法确定扫描日")
    latest = dates.max()
    if requested and latest != requested:
        raise ValueError(f"{requested} 没有{source_label}数据（不是交易日，或数据源还没更新），"
                         f"它之前最近的交易日是 {latest}")
    return latest
