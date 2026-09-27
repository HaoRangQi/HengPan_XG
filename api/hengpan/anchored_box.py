"""
末端锚定横盘箱体的纯计算部分：用最新一根 K 线定箱体，用它之前的 LOOKBACK 根 K 线验箱体。
只做计算，不联网、不读写文件。

一次扫描通常要按多组规则各算一遍，所以把日线表先转成 numpy 数组（extract_series），
多组规则复用同一份，避免按规则反复切片 DataFrame。

箱体有两种定法：
- fixed 固定箱高：十字星的中点是上轨，普通 K 线的中点是中轨，箱高是固定参数；
- amplitude 振幅倍数：不区分十字星，末端 K 线的最高价往上、最低价往下各延伸若干倍末端振幅，箱高随末端 K 线变化。
"""
import math

import numpy as np

# 默认参数（方案文档第 10 节），扫描时可以按请求覆盖
DOJI_AMPLITUDE = 0.005   # 十字星振幅上限：末端振幅不超过它算十字星
BOX_HEIGHT = 0.04        # 箱体固定高度
LOOKBACK = 80            # 回验根数，不含末端这一根
MAX_BREACH = 2           # 回验区间允许越界的最多根数
BOX_TYPE = "fixed"       # 箱体模式：fixed 固定箱高 / amplitude 振幅倍数
AMP_MULTIPLE = 1.0       # 振幅模式：末端 K 线最高价往上、最低价往下各延伸几倍末端振幅
EPS = 1e-9               # 相对容差，只用来消除浮点误差，不改变规则
BOUNDARY_BAND = 0.001    # 末端振幅离十字星分界不超过 0.1 个百分点，算「分界附近」

PRICE_COLUMNS = ("open", "high", "low", "close")
EXTRA_COLUMNS = ("amount", "turn")


def extract_series(df):
    """把日线表转成 numpy 数组。多组规则共用同一份，省掉重复的 DataFrame 切片开销。"""
    series = {column: df[column].to_numpy(dtype=float) for column in PRICE_COLUMNS}
    for column in EXTRA_COLUMNS:
        series[column] = df[column].to_numpy(dtype=float) if column in df else None
    series["date"] = df["date"].to_numpy() if "date" in df else None
    return series


def anchor_box(high, low, mode, box_height=BOX_HEIGHT):
    """把箱体钉在末端 K 线上：十字星的中点是上轨，普通 K 线的中点是中轨。返回 (上轨, 下轨)。"""
    mid = (high + low) / 2
    if mode == "doji":
        return mid, mid * (1 - box_height)
    return mid * (1 + box_height / 2), mid * (1 - box_height / 2)


def amplitude_box(high, low, multiple=AMP_MULTIPLE):
    """振幅模式：末端 K 线最高价往上、最低价往下各延伸 multiple 倍振幅（最高 − 最低）。返回 (上轨, 下轨)，下轨不低于 0。"""
    span = (high - low) * multiple
    return high + span, max(low - span, 0.0)


def _mean(values):
    """一段数值的均值，忽略空值；全为空值或没有这一列时返回 None。"""
    if values is None or not len(values) or not np.isfinite(values).any():
        return None
    value = float(np.nanmean(values))
    return value if math.isfinite(value) else None


def check_series(series, doji_amplitude=DOJI_AMPLITUDE, box_height=BOX_HEIGHT,
                 lookback=LOOKBACK, max_breach=MAX_BREACH, mode=None,
                 box_type=BOX_TYPE, amp_multiple=AMP_MULTIPLE):
    """
    按一组规则判断这只股票现在是否处在末端锚定的横盘箱体里。

    series：extract_series 的返回值，最后一个元素是末端 K 线。
    box_type：fixed 用 doji_amplitude、box_height 锚定固定箱高；amplitude 用 amp_multiple 按末端振幅定箱体，
              此时结果的 mode 固定为 "amplitude"。
    mode：只对 fixed 生效。默认按末端振幅判定；传 "doji" 或 "normal" 时强制按该模式锚定，只用于统计分界漏选。
    有效 K 线不足 lookback + 1 根时返回 None。
    """
    if box_type not in ("fixed", "amplitude"):
        raise ValueError("box_type must be 'fixed' or 'amplitude'")
    high, low, close = series["high"], series["low"], series["close"]
    if len(close) < lookback + 1:
        return None

    amplitude = (high[-1] - low[-1]) / close[-1]
    if box_type == "amplitude":
        mode = "amplitude"
        upper, lower = amplitude_box(high[-1], low[-1], amp_multiple)
    else:
        if mode is None:
            mode = "doji" if amplitude <= doji_amplitude * (1 + EPS) else "normal"
        upper, lower = anchor_box(high[-1], low[-1], mode, box_height)

    # 回验区间：末端之前的 lookback 根，不含末端。价格恰好等于上轨或下轨算在箱内。
    start = len(close) - lookback - 1
    window = slice(start, -1)
    actual_window = slice(start, None)
    upper_cmp, lower_cmp = upper * (1 + EPS), lower * (1 - EPS)
    hist_open, hist_close = series["open"][window], close[window]
    breach_full = int(np.count_nonzero((high[window] > upper_cmp) | (low[window] < lower_cmp)))
    breach_body = int(np.count_nonzero((np.maximum(hist_open, hist_close) > upper_cmp) |
                                       (np.minimum(hist_open, hist_close) < lower_cmp)))

    amount, turn, date = series["amount"], series["turn"], series["date"]
    actual_high = float(np.nanmax(high[actual_window]))
    actual_low = float(np.nanmin(low[actual_window]))
    return {
        "mode": mode,
        "amplitude": float(amplitude),
        "upper": float(upper),
        "lower": float(lower),
        "actual_range": (actual_high - actual_low) / actual_low,
        "breach_full": breach_full,
        "breach_body": breach_body,
        "passed_full": breach_full <= max_breach,
        "passed_body": breach_body <= max_breach,
        "avg_amount": _mean(amount[window] if amount is not None else None),
        "avg_turn": _mean(turn[window] if turn is not None else None),
        "lookback_start": str(date[start]) if date is not None else None,
    }


def check_anchored_box(df, **rule):
    """
    check_series 的 DataFrame 版本，用于单组规则和测试。

    df：单只股票日 K 线，前复权、已删掉停牌行、按日期升序，最后一行是末端 K 线；
        必须有 open/high/low/close 列，有 date/amount/turn 列时一并输出。
    """
    return check_series(extract_series(df), **rule)
