"""容刺箱体纯计算：用实体中心价寻找主体区间，允许少量离散实体刺破。"""
import math

import numpy as np

from .anchored_box import EPS, _mean

MAX_CONSECUTIVE_BREACH = 1
MAX_SEGMENT_SHIFT_RATIO = 0.4


def _longest_true_run(values):
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _best_box(centers, box_height):
    """返回固定最大宽度内覆盖最多中心价的区间，平局时优先更贴近中位数。"""
    ordered = np.sort(centers)
    median = float(np.median(ordered))
    best = None
    right = 0
    for left, lower in enumerate(ordered):
        right = max(right, left)
        upper = lower * (1 + box_height)
        while right + 1 < len(ordered) and ordered[right + 1] <= upper * (1 + EPS):
            right += 1
        count = right - left + 1
        distance = abs((lower + upper) / 2 - median)
        candidate = (count, -distance, -float(lower), float(lower), float(ordered[right]))
        if best is None or candidate[:3] > best[:3]:
            best = candidate
    # 选择阶段用价格点作为滑窗边界；输出阶段把完整允许宽度围绕被覆盖主体的中点展开，
    # 避免“中心价正好等于下轨”导致一半正常实体天然越界。
    midpoint = (best[3] + best[4]) / 2
    lower = 2 * midpoint / (2 + box_height)
    return lower, lower * (1 + box_height)


def _segment_shift_ratio(centers, box_height):
    """首尾各三分之一的中心价偏移，占允许箱宽的比例。"""
    segment_size = max(1, len(centers) // 3)
    first_center = float(np.median(centers[:segment_size]))
    last_center = float(np.median(centers[-segment_size:]))
    midpoint = (first_center + last_center) / 2
    relative_shift = abs(last_center - first_center) / midpoint
    return relative_shift / max(box_height, EPS)


def check_tolerant_series(series, box_height=0.04, lookback=80, max_breach=4,
                          max_consecutive_breach=MAX_CONSECUTIVE_BREACH, **_unused):
    """
    在最近 ``lookback`` 根 K 线中寻找容刺箱体。

    实体中心 ``(open + close) / 2`` 只负责确定覆盖最多数据的主体区间；箱体确定后，
    open/close 任一端越轨才计实体刺。high/low 越轨只计入 ``breach_full`` 供展示，
    不影响本模式的通过结果。
    """
    open_, high, low, close = (series[name] for name in ("open", "high", "low", "close"))
    if len(close) < lookback:
        return None

    start = len(close) - lookback
    window = slice(start, None)
    win_open, win_close = open_[window], close[window]
    centers = (win_open + win_close) / 2
    if not np.isfinite(centers).all() or np.any(centers <= 0):
        return None

    lower, upper = _best_box(centers, box_height)
    upper_cmp, lower_cmp = upper * (1 + EPS), lower * (1 - EPS)
    body_breaches = ((np.maximum(win_open, win_close) > upper_cmp) |
                     (np.minimum(win_open, win_close) < lower_cmp))
    full_breaches = ((high[window] > upper_cmp) | (low[window] < lower_cmp))
    breach_body = int(np.count_nonzero(body_breaches))
    breach_full = int(np.count_nonzero(full_breaches))
    longest = _longest_true_run(body_breaches)
    segment_shift_ratio = _segment_shift_ratio(centers, box_height)
    shifted_box = segment_shift_ratio > MAX_SEGMENT_SHIFT_RATIO * (1 + EPS)
    passed = (breach_body <= max_breach and
              longest <= max_consecutive_breach and
              not shifted_box)

    actual_high = float(np.nanmax(high[window]))
    actual_low = float(np.nanmin(low[window]))
    last_amplitude = (high[-1] - low[-1]) / close[-1]
    date = series.get("date")
    amount = series.get("amount")
    turn = series.get("turn")
    actual_range = ((actual_high - actual_low) / actual_low
                    if actual_low > 0 and math.isfinite(actual_low) else None)
    return {
        "mode": "tolerant",
        "amplitude": float(last_amplitude),
        "upper": upper,
        "lower": lower,
        "actual_range": actual_range,
        "breach_full": breach_full,
        "breach_body": breach_body,
        "longest_consecutive_breach": longest,
        "segment_shift_ratio": segment_shift_ratio,
        "shifted_box": shifted_box,
        "over_amplitude": False,
        "passed_full": passed,
        "passed_body": passed,
        "avg_amount": _mean(amount[window] if amount is not None else None),
        "avg_turn": _mean(turn[window] if turn is not None else None),
        "lookback_start": str(date[start]) if date is not None else None,
    }
