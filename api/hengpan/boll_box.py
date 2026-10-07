"""布林矩形：初始首尾与中点复核一次，再向前逐根扩展，首次失败即停。"""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .anchored_box import EPS, _mean

BOLL_PERIOD = 30
BOLL_MULTIPLIER = 2.0
MIN_BOX_BARS = 80
OBSERVE_BARS = 30
RECTANGLE_TOLERANCE = 0.2
# 旧请求和旧历史的字段仍可解析，但新算法不使用整段极差阈值。
RAIL_TOLERANCE = 0.05
BANDWIDTH_TOLERANCE = 1.5
LEGACY_RULE_FIELDS = ("boll_period", "boll_multiplier", "min_box_bars",
                      "rail_tolerance", "bandwidth_tolerance")
RULE_FIELDS = ("boll_period", "boll_multiplier", "min_box_bars", "rectangle_tolerance")


def required_bars(params):
    """按用户约定预留完整 n 根预热，例如 50 根区间加 20 根预热。"""
    return params.get("boll_period", BOLL_PERIOD) + params.get("min_box_bars", MIN_BOX_BARS)


def _rectangle_error(upper, lower, widths, left, right):
    """两个位置的上下轨四点偏离水平矩形的程度；退化箱高不算矩形。"""
    if min(widths[left], widths[right]) <= np.finfo(float).eps * 64 or min(lower[left], lower[right]) <= 0:
        return None
    average_height = (widths[left] + widths[right]) / 2
    return float(max(abs(upper[left] - upper[right]), abs(lower[left] - lower[right])) / average_height)


def check_boll_box_series(series, boll_period=BOLL_PERIOD, boll_multiplier=BOLL_MULTIPLIER,
                          min_box_bars=MIN_BOX_BARS, rectangle_tolerance=RECTANGLE_TOLERANCE,
                          **_unused):
    prices = np.column_stack([series[name] for name in ("open", "high", "low", "close")])
    invalid = ~np.isfinite(prices).all(axis=1) | (prices <= 0).any(axis=1)
    invalid |= (prices[:, 1] < prices[:, [0, 3]].max(axis=1)) | (prices[:, 2] > prices[:, [0, 3]].min(axis=1))
    volume = series.get("volume")
    if volume is not None:
        invalid |= ~np.isfinite(volume) | (volume <= 0)
    broken = np.flatnonzero(invalid)
    valid_start = int(broken[-1] + 1) if len(broken) else 0
    close = series["close"][valid_start:]
    if len(close) < boll_period + min_box_bars:
        return None

    # 预计算完整滚动轨道，供初始中点复核和向前逐根取头点使用。
    # 常规 BOLL 包含当前根；完整 n 根预热的最老一根是额外余量，不计入区间。
    scale = float(close[-1])
    windows = sliding_window_view(close / scale - 1, boll_period)
    middle = windows.mean(axis=1) + 1
    sigma = windows.std(axis=1, ddof=0)
    upper, lower = middle + boll_multiplier * sigma, middle - boll_multiplier * sigma
    widths = 2 * boll_multiplier * sigma
    initial_head = len(middle) - min_box_bars
    tail = len(middle) - 1
    tail_upper, tail_lower = float(upper[-1]), float(lower[-1])
    tail_width = float(widths[-1])
    chosen = initial_head
    error = _rectangle_error(upper, lower, widths, initial_head, tail)
    passed = error is not None and error <= rectangle_tolerance + EPS
    if passed:
        # 仅初始 B 根复核一次；偶数长度取靠左的中间根。
        midpoint = (initial_head + tail) // 2
        half_errors = (_rectangle_error(upper, lower, widths, initial_head, midpoint),
                       _rectangle_error(upper, lower, widths, midpoint, tail))
        passed = all(value is not None and value <= rectangle_tolerance + EPS for value in half_errors)
    if passed:
        # 末端固定，逐根向前；不移动中点，不跳过坏点，保留最后合格的头点。
        for index in range(initial_head - 1, 0, -1):
            candidate_error = _rectangle_error(upper, lower, widths, index, tail)
            if candidate_error is None or candidate_error > rectangle_tolerance + EPS:
                break
            chosen, error = index, candidate_error

    length = len(middle) - chosen
    start = len(series["close"]) - length
    window = slice(start, None)
    head_upper, head_lower = float(upper[chosen] * scale), float(lower[chosen] * scale)
    tail_upper, tail_lower = tail_upper * scale, tail_lower * scale
    # 末端状态仍只作提示，参照前一根已形成的轨道，不让末端撑大自己的参考边界。
    tail_state, tail_bars = "inside", 0
    for offset in range(1, min(3, len(middle) - 1) + 1):
        price = close[-offset] / scale
        state = ("above" if price > upper[-offset - 1] * (1 + EPS) else
                 "below" if price < lower[-offset - 1] * (1 - EPS) else "inside")
        if not tail_bars:
            tail_state = state
        if state == "inside" or state != tail_state:
            break
        tail_bars += 1

    high, low = series["high"], series["low"]
    date, amount, turn = (series.get(name) for name in ("date", "amount", "turn"))
    actual_high, actual_low = float(np.max(high[window])), float(np.min(low[window]))
    # 越界数量是四点连线内的描述量，不参与筛选。
    upper_edge = np.linspace(head_upper, tail_upper, length)
    lower_edge = np.linspace(head_lower, tail_lower, length)
    return {
        "mode": "boll_box", "boll_geometry": "endpoints_v1",
        "boll_period": boll_period, "boll_multiplier": boll_multiplier,
        "box_bars": length, "rectangle_error": error,
        "head_upper": head_upper, "head_lower": head_lower,
        "tail_upper": tail_upper, "tail_lower": tail_lower,
        "bandwidth": float(tail_width / middle[-1]),
        "boll_start": str(date[valid_start]) if date is not None else None,
        "lookback_start": str(date[start]) if date is not None else None,
        "box_end": str(date[-1]) if date is not None else None,
        "history_limited": bool(passed and chosen == 1),
        "upper": tail_upper, "lower": tail_lower,
        "actual_range": (actual_high - actual_low) / actual_low,
        "amplitude": float((high[-1] - low[-1]) / close[-1]),
        "tail_state": tail_state, "tail_bars": tail_bars,
        "breach_full": int(np.count_nonzero((high[window] > upper_edge) | (low[window] < lower_edge))),
        "breach_body": int(np.count_nonzero((series["open"][window] > upper_edge) |
                                            (series["open"][window] < lower_edge) |
                                            (series["close"][window] > upper_edge) |
                                            (series["close"][window] < lower_edge))),
        "over_amplitude": False, "passed_full": passed, "passed_body": passed,
        "avg_amount": _mean(amount[window] if amount is not None else None),
        "avg_turn": _mean(turn[window] if turn is not None else None),
    }
