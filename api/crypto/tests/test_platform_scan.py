import unittest

import numpy as np
import pandas as pd

from fastapi import HTTPException

from api.crypto.platform_router import (
    CryptoCategoryParams,
    CryptoPlatformScanRequest,
    _params_for,
    _validate_request,
)
from api.crypto.platform_scan import (
    CATEGORY_DEFAULTS,
    build_crypto_frame,
    analyze_crypto_platform,
    category_defaults,
    normalize_crypto_symbols,
)


def bars(count=120, start=100.0, drift=0.0):
    values = [start + drift * index for index in range(count)]
    return pd.DataFrame({
        "symbol": ["BTCUSDT"] * count,
        "date": pd.date_range("2026-01-01", periods=count, freq="h").strftime("%Y-%m-%d %H:%M:%S"),
        "open": values,
        "high": [value * 1.002 for value in values],
        "low": [value * 0.998 for value in values],
        "close": values,
        "volume": np.full(count, 1000.0),
        "quote_asset_volume": np.full(count, 100000.0),
    })


class CryptoPlatformScanTest(unittest.TestCase):
    def test_category_defaults_keep_both_categories_and_different_box_widths(self):
        self.assertEqual(list(CATEGORY_DEFAULTS), ["perpetual", "tradifi"])
        self.assertEqual(category_defaults("perpetual")["box_threshold"], 0.15)
        self.assertEqual(category_defaults("tradifi")["box_threshold"], 0.04)

    def test_symbol_selection_deduplicates_categories_and_symbols(self):
        symbols = normalize_crypto_symbols([
            {"symbol": "BTCUSDT", "category": "perpetual", "status": "TRADING"},
            {"symbol": "BTCUSDT", "category": "perpetual", "status": "TRADING"},
            {"symbol": "BTCUSDT", "category": "tradifi", "status": "TRADING"},
            {"symbol": "XAUUSDT", "category": "tradifi", "status": "TRADING"},
        ], categories=["tradifi", "perpetual"], selected_symbols=["BTCUSDT"])
        self.assertEqual([(item["category"], item["symbol"]) for item in symbols],
                         [("perpetual", "BTCUSDT"), ("tradifi", "BTCUSDT")])

    def test_crypto_frame_derives_fractional_returns_and_amount(self):
        frame = build_crypto_frame(bars(3))
        self.assertIn("pctChg", frame)
        self.assertIn("amount", frame)
        self.assertTrue(np.isnan(frame.iloc[0]["pctChg"]))
        self.assertEqual(frame.iloc[1]["amount"], 100000.0)

    def test_platform_analysis_returns_window_reasons_for_stable_series(self):
        result = analyze_crypto_platform(bars(), windows=[40, 80], box_threshold=0.15,
                                         ma_diff_threshold=0.01, volatility_threshold=0.017,
                                         use_volume_analysis=False, use_box_detection=False)
        self.assertTrue(result["is_platform"])
        self.assertEqual(result["platform_windows"], [40, 80])
        self.assertEqual(set(result["selection_reasons"]), {40, 80})

    def test_reasons_are_labelled_in_bars_not_trading_days(self):
        """这个页面扫的是 60 分钟线，共用分析器给出的「N日平台期」必须换成「N根K线平台期」。"""
        result = analyze_crypto_platform(bars(), windows=[40], box_threshold=0.15,
                                         ma_diff_threshold=0.01, volatility_threshold=0.017,
                                         use_volume_analysis=False, use_box_detection=False)
        reason = result["selection_reasons"][40]
        self.assertIn("40根K线平台期", reason)
        self.assertNotIn("40日平台期", reason)

    def test_volume_thresholds_are_per_category_and_not_borrowed_from_a_share(self):
        """实测：TradFi 周末量归零把量能波动系数抬到 1.9，沿用 A 股的 0.5 会一个不剩。"""
        for category in CATEGORY_DEFAULTS:
            params = category_defaults(category)
            self.assertIn("volume_change_threshold", params)
            self.assertIn("volume_stability_threshold", params)
        self.assertGreater(category_defaults("tradifi")["volume_stability_threshold"], 1.0)
        self.assertGreater(category_defaults("perpetual")["volume_change_threshold"],
                           category_defaults("tradifi")["volume_change_threshold"])

    def test_category_defaults_feed_the_analyzer_signature_directly(self):
        """CATEGORY_DEFAULTS 的键必须正好是 analyze_crypto_platform 的形参名（路由按 **params 展开）。"""
        for category in CATEGORY_DEFAULTS:
            analyze_crypto_platform(bars(), windows=[40], **category_defaults(category),
                                    use_volume_analysis=True, use_box_detection=False)

    def test_breakthrough_confirmation_reaches_the_analyzer(self):
        """突破确认以前在适配层被硬编码成关闭，开关要真的传到分析器。"""
        result = analyze_crypto_platform(bars(count=120, drift=0.05), windows=[40],
                                         **category_defaults("perpetual"),
                                         use_box_detection=False,
                                         use_breakthrough_confirmation=True,
                                         breakthrough_confirmation_days=3)
        self.assertIn("is_platform", result)


class CryptoPlatformRequestTest(unittest.TestCase):
    def test_category_overrides_accept_volume_thresholds_above_one(self):
        request = CryptoPlatformScanRequest(category_params={
            "tradifi": CryptoCategoryParams(volume_stability_threshold=2.3)})
        params = _params_for("tradifi", request)
        self.assertEqual(params["volume_stability_threshold"], 2.3)
        # 未覆盖的键仍取默认值
        self.assertEqual(params["box_threshold"], CATEGORY_DEFAULTS["tradifi"]["box_threshold"])

    def test_window_weights_must_cover_every_window(self):
        request = CryptoPlatformScanRequest(windows=[40, 80], use_window_weights=True,
                                            window_weights={40: 1.0})
        with self.assertRaises(HTTPException) as caught:
            _validate_request(request)
        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("80", caught.exception.detail)

    def test_window_weights_sum_must_be_positive(self):
        request = CryptoPlatformScanRequest(windows=[40], use_window_weights=True,
                                            window_weights={40: 0})
        with self.assertRaises(HTTPException):
            _validate_request(request)

    def test_window_weights_are_ignored_when_switch_is_off(self):
        _validate_request(CryptoPlatformScanRequest(windows=[40, 80], window_weights={40: 1.0}))

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            _validate_request(CryptoPlatformScanRequest(categories=["stocks"]))
        self.assertEqual(caught.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
