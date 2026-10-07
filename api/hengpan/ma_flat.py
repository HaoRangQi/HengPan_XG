"""均线走平模式：末端锚定的自适应区间，不预设价格箱体或区间涨幅。"""
import numpy as np
import pandas as pd

from .anchored_box import EPS, _mean

MA_PERIOD = 30
MIN_FLAT_BARS = 30
MA_TOLERANCE = 0.01
MAX_EFFICIENCY_RATIO = 0.5
RULE_FIELDS = ("ma_period", "min_flat_bars", "ma_tolerance", "max_efficiency_ratio")
# 仅用于联网日线取数的资源边界；本地 A/U 行情读取全部已存历史。
REMOTE_HISTORY_BARS = 1000


def required_bars(params):
    return params.get("ma_period", MA_PERIOD) + params.get("min_flat_bars", MIN_FLAT_BARS) - 1


from ..data_quality import closed_frame, continuous_frame


def check_ma_flat_series(series, ma_period=MA_PERIOD, min_flat_bars=MIN_FLAT_BARS,
                         ma_tolerance=MA_TOLERANCE, max_efficiency_ratio=MAX_EFFICIENCY_RATIO,
                         **_unused):
    """先寻找最长均线水平尾部，再在该区间计算 ER；ER 不用于提前停止搜索。"""
    prices = np.column_stack([series[name] for name in ("open", "high", "low", "close")])
    invalid = np.flatnonzero(~np.isfinite(prices).all(axis=1) | (prices <= 0).any(axis=1))
    valid_start = int(invalid[-1] + 1) if len(invalid) else 0
    close = series["close"][valid_start:]
    if len(close) < ma_period + min_flat_bars - 1:
        return None

    # 以最新价格平移后求前缀和，减少长历史、大面值价格的相减损失。
    sums = np.concatenate(([0.0], np.cumsum(close - close[-1])))
    averages = (sums[ma_period:] - sums[:-ma_period]) / ma_period + close[-1]
    latest = float(averages[-1])
    low_ma = high_ma = latest
    length = 0
    for value in averages[::-1]:
        lower, upper = min(low_ma, float(value)), max(high_ma, float(value))
        if upper - lower > latest * (ma_tolerance + EPS):
            break
        low_ma, high_ma = lower, upper
        length += 1

    start = len(series["close"]) - length
    window = slice(start, None)
    window_close = series["close"][window]
    path = float(np.sum(np.abs(np.diff(window_close))))
    efficiency = float(abs(window_close[-1] - window_close[0]) / path) if path > 0 else 0.0
    passed = length >= min_flat_bars and efficiency <= max_efficiency_ratio + EPS
    high, low = series["high"], series["low"]
    upper, lower = float(np.max(high[window])), float(np.min(low[window]))

    # 最近三根不参与参照范围，避免刚突破的 K 线把自己的边界撑大；状态不作为淘汰条件。
    tail_size = min(3, max(0, length - 1))
    tail_state, tail_bars = "inside", 0
    if tail_size:
        reference_upper = float(np.max(high[start:-tail_size]))
        reference_lower = float(np.min(low[start:-tail_size]))
        for price in window_close[-tail_size:][::-1]:
            state = ("above" if price > reference_upper * (1 + EPS) else
                     "below" if price < reference_lower * (1 - EPS) else "inside")
            if not tail_bars:
                tail_state = state
            if state == "inside" or state != tail_state:
                break
            tail_bars += 1

    date, amount, turn = (series.get(name) for name in ("date", "amount", "turn"))
    return {
        "mode": "ma_flat",
        "ma_period": ma_period,
        "flat_bars": length,
        "ma_value": latest,
        "ma_range": (high_ma - low_ma) / latest,
        "efficiency_ratio": efficiency,
        "price_ma_distance": float(window_close[-1] / latest - 1),
        "tail_state": tail_state,
        "tail_bars": tail_bars,
        "history_limited": length == len(averages),
        "amplitude": float((high[-1] - low[-1]) / window_close[-1]),
        # 价格上下沿仅作区间展示，绝不参与均线模式筛选。
        "upper": upper,
        "lower": lower,
        "actual_range": (upper - lower) / lower,
        "breach_full": 0,
        "breach_body": 0,
        "over_amplitude": False,
        "passed_full": passed,
        "passed_body": passed,
        "avg_amount": _mean(amount[window] if amount is not None else None),
        "avg_turn": _mean(turn[window] if turn is not None else None),
        "lookback_start": str(date[start]) if date is not None else None,
    }
