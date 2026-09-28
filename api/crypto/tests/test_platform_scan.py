import unittest

import numpy as np
import pandas as pd

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


if __name__ == "__main__":
    unittest.main()
