"""Shared scan input checks; gaps never become synthetic flat candles."""
import numpy as np
import pandas as pd

def closed_frame(frame, frequency, now=None):
    """A 股分钟时间为收盘时刻，加密时间为开盘时刻；只让完整 K 线参与新模式。"""
    if frame.empty:
        return frame
    current = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="Asia/Shanghai")
    if current.tzinfo is not None:
        current = current.tz_convert("Asia/Shanghai").tz_localize(None)
    moments = pd.to_datetime(frame["date"], errors="coerce")
    if frequency == "1h":
        ends = moments + pd.Timedelta(hours=1)
    elif frequency == "d":
        ends = moments.dt.normalize() + pd.Timedelta(hours=15)
    else:
        ends = moments
    return frame.loc[ends <= current].reset_index(drop=True)


def continuous_frame(frame, frequency, trading_days=None):
    """均线预热也不能跨缺口；保留最后一个缺口之后的连续数据，不误删更晚的新平台。"""
    if len(frame) < 2:
        return frame
    moments = pd.to_datetime(frame["date"], errors="coerce")
    gaps = np.zeros(len(frame) - 1, dtype=bool)
    if frequency == "1h":
        gaps = np.diff(moments.astype("int64").to_numpy()) != pd.Timedelta(hours=1).value
    else:
        calendar = {day: index for index, day in enumerate(trading_days or [])}
        days = frame["date"].astype(str).str[:10].tolist()
        sessions = {time: index for index, time in enumerate(("10:30:00", "11:30:00", "14:00:00", "15:00:00"))}
        slots = frame["date"].astype(str).str[11:19].map(sessions).tolist()
        for index in range(1, len(frame)):
            previous, current = days[index - 1], days[index]
            day_step = (calendar[current] - calendar[previous]
                        if current in calendar and previous in calendar else None)
            if frequency == "d":
                gaps[index - 1] = current <= previous or (day_step is not None and day_step != 1)
            elif pd.notna(slots[index - 1]) and pd.notna(slots[index]):
                if current == previous:
                    gaps[index - 1] = slots[index] - slots[index - 1] != 1
                else:
                    gaps[index - 1] = (slots[index - 1] != 3 or slots[index] != 0 or
                                       current <= previous or (day_step is not None and day_step != 1))
            elif day_step is not None:
                gaps[index - 1] = day_step not in (0, 1)
    positions = np.flatnonzero(gaps)
    start = int(positions[-1] + 1) if len(positions) else 0
    result = frame.iloc[start:].reset_index(drop=True)
    result.attrs["continuity_gap"] = bool(len(positions))
    return result



def st_status(value):
    """Only explicit daily-source status establishes ST or normal status."""
    if value is None or pd.isna(value):
        return None
    return {"1": True, "0": False}.get(str(value))


def prepare_scan_frame(frame, windows, frequency, scan_date, trading_days=None,
                       required_history=0, now=None):
    """Return continuous closed data, eligible bar windows, and a skip reason.

    A date anchor checks its trading day; a timestamp anchor checks the exact bar.
    Required history is used for independent enabled analyses (e.g. low position).
    """
    data = closed_frame(frame, frequency, now=now)
    if data.empty:
        return data, [], "stale"
    if not matches_scan_anchor(data, scan_date):
        return data, [], "stale"
    continuous = continuous_frame(data, frequency, trading_days)
    eligible = [window for window in windows if len(continuous) >= max(window, required_history)]
    if eligible:
        return continuous, eligible, None
    needed = max(min(windows, default=1), required_history)
    reason = "gap" if len(data) >= needed and continuous.attrs.get("continuity_gap") else "insufficient"
    return continuous, [], reason


def matches_scan_anchor(frame, anchor):
    """Compare normalized timestamps, or a legacy explicit scan date."""
    if frame.empty:
        return False
    latest = str(frame["date"].iloc[-1])
    return latest[:10] == str(anchor) if len(str(anchor)) == 10 else pd.Timestamp(latest) == pd.Timestamp(anchor)
