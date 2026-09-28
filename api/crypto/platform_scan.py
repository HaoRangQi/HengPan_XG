"""本地加密平台扫描：把 A 股平台分析器复用到 crypto.db 的 1 小时 K 线。"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from ..analyzers.combined_analyzer import analyze_stock
from ..hengpan.anchored_box import extract_series
from ..hengpan.scanner import evaluate_rule
from . import db
from .reader import load_kline

# 阈值按本地 1 小时线实测标定（527 个加密永续 + 200 个 TradFi，80 根窗口）：
# 振幅中位 0.124 / 0.047，均线粘合度中位 0.0100 / 0.0042，量比中位 0.72 / 0.39，
# 量稳中位 0.78 / 1.88。量能两项尤其不能用 A 股的 0.5 —— TradFi 有交易时段，
# 周末量归零把波动系数拉到 1.9，按 0.5 筛会一个不剩。
CATEGORY_DEFAULTS = {
    "perpetual": {
        "box_threshold": 0.15, "ma_diff_threshold": 0.010, "volatility_threshold": 0.017,
        "volume_change_threshold": 1.0, "volume_stability_threshold": 1.2,
    },
    "tradifi": {
        "box_threshold": 0.04, "ma_diff_threshold": 0.003, "volatility_threshold": 0.004,
        "volume_change_threshold": 0.6, "volume_stability_threshold": 2.3,
    },
}
CATEGORY_LABELS = {"perpetual": "加密永续", "tradifi": "TradFi 永续"}


def category_defaults(category: str) -> Dict[str, float]:
    if category not in CATEGORY_DEFAULTS:
        raise ValueError(f"未知加密类别：{category}")
    return dict(CATEGORY_DEFAULTS[category])


def normalize_crypto_symbols(symbols: Iterable[Dict[str, Any]], categories=None,
                             selected_symbols=None) -> List[Dict[str, Any]]:
    categories = list(categories or db.CATEGORIES)
    allowed = set(categories)
    selected = set(selected_symbols or [])
    result = []
    seen = set()
    for item in symbols:
        symbol = item.get("symbol")
        category = item.get("category")
        identity = (category, symbol)
        if not symbol or category not in allowed or identity in seen:
            continue
        if selected and symbol not in selected:
            continue
        seen.add(identity)
        result.append(dict(item))
    return result


def build_crypto_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """把本地 reader 输出映射成 A 股分析器所需的最小列集合。"""
    if frame.empty:
        return frame
    result = frame.copy()
    for column in ("open", "high", "low", "close", "volume", "quote_asset_volume"):
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    result["pctChg"] = result["close"].pct_change()
    result["amount"] = result["quote_asset_volume"]
    return result.dropna(subset=["open", "high", "low", "close"])


def load_crypto_frame(conn, symbol_info: Dict[str, Any], limit: int = 1500) -> pd.DataFrame:
    frame = load_kline(conn, "1h", [symbol_info["category"]], [symbol_info["symbol"]])
    return build_crypto_frame(frame.tail(limit).reset_index(drop=True))


def analyze_crypto_platform(frame: pd.DataFrame, windows, *, box_threshold,
                            ma_diff_threshold, volatility_threshold,
                            volume_change_threshold=0.5,
                            volume_stability_threshold=0.5,
                            volume_increase_threshold=1.5,
                            use_volume_analysis=False,
                            use_breakthrough_prediction=False,
                            use_breakthrough_confirmation=False,
                            breakthrough_confirmation_days=1,
                            use_window_weights=False,
                            window_weights=None,
                            use_box_detection=True,
                            box_quality_threshold=0.6):
    # 低位判断与快速下跌不开放：decline_analyzer 的回溯窗口按「根数」取、下跌周期按
    # 真实日历天算，1 小时线上两套口径对不上（本地只存 60 天≈1440 根，日历天约束恒真）。
    result = analyze_stock(
        frame, list(windows),
        box_threshold=box_threshold,
        ma_diff_threshold=ma_diff_threshold,
        volatility_threshold=volatility_threshold,
        volume_change_threshold=volume_change_threshold,
        volume_stability_threshold=volume_stability_threshold,
        volume_increase_threshold=volume_increase_threshold,
        use_volume_analysis=use_volume_analysis,
        use_breakthrough_prediction=use_breakthrough_prediction,
        use_window_weights=use_window_weights,
        window_weights=window_weights or {},
        use_low_position=False,
        use_rapid_decline_detection=False,
        use_breakthrough_confirmation=use_breakthrough_confirmation,
        breakthrough_confirmation_days=breakthrough_confirmation_days,
        use_box_detection=use_box_detection,
        box_quality_threshold=box_quality_threshold,
    )
    # The shared analyzer speaks in A-share daily-window terminology. Crypto-U
    # scans local 60-minute bars, so keep the analysis intact but label reasons
    # with the actual unit shown by this page.
    result["selection_reasons"] = {
        window: str(reason).replace(f"{window}日平台期", f"{window}根K线平台期")
        for window, reason in result.get("selection_reasons", {}).items()
    }
    return result


def analyze_crypto_hengpan(frame: pd.DataFrame, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    series = extract_series(frame)
    matches = {}
    for rule in rules:
        result = evaluate_rule(series, rule["params"])
        if result and result["passed_body"]:
            matches[rule["id"]] = result
    return {"matches": matches, "series": series}


def crypto_kline_records(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    columns = ["date", "open", "high", "low", "close", "volume", "amount"]
    data = frame[[column for column in columns if column in frame]].astype(object)
    data = data.where(pd.notna(data), None)
    return data.to_dict(orient="records")
