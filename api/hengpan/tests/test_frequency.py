"""周期契约和分钟 K 线格式回归测试。"""
import inspect
import unittest
import tempfile
from unittest.mock import patch

import pandas as pd
from pydantic import ValidationError

from api.hengpan.fetcher import clean_kline, fetch_kline, resolve_scan_date
from api.hengpan.router import HengpanScanRequest
from api.hengpan.scanner import analyze_stock, build_item, fetch_range, scan_anchored_box
from api.hengpan import history


class FrequencyContractTest(unittest.TestCase):
    def test_hengpan_defaults_to_60_minutes(self):
        self.assertEqual(HengpanScanRequest().frequency, "60")
        self.assertEqual(HengpanScanRequest(frequency="d").frequency, "d")
        for function in (fetch_range, build_item, analyze_stock, scan_anchored_box):
            with self.subTest(function=function.__name__):
                self.assertEqual(inspect.signature(function).parameters["frequency"].default, "60")

    def test_invalid_frequency_is_rejected(self):
        with self.assertRaises(ValidationError):
            HengpanScanRequest(frequency="5")

    def test_minute_time_is_normalised_and_sorted(self):
        frame = pd.DataFrame([
            {"date": "2026-09-25", "time": "20260925150000000", "open": "2", "high": "3",
             "low": "1", "close": "2.5", "volume": "10", "amount": "20"},
            {"date": "2026-09-25", "time": "20260925103000000", "open": "1", "high": "2",
             "low": "1", "close": "1.5", "volume": "5", "amount": "8"},
        ])
        result = clean_kline(frame, frequency="60")
        self.assertEqual(result["date"].tolist(), ["2026-09-25 10:30:00", "2026-09-25 15:00:00"])
        self.assertEqual(result["close"].tolist(), [1.5, 2.5])

    @patch("api.hengpan.fetcher.query_kline")
    def test_fetch_kline_uses_minute_frequency(self, query):
        query.return_value = pd.DataFrame([
            {"date": "2026-09-25", "time": "20260925103000000", "open": "1", "high": "2",
             "low": "1", "close": "1.5", "volume": "5", "amount": "8"},
        ])
        fetch_kline("sh.600000", "2026-09-01", "2026-09-25", frequency="60")
        args, kwargs = query.call_args
        self.assertEqual(args[0], "sh.600000")
        self.assertEqual(kwargs["frequency"], "60")
        self.assertIn("time", args[1])

    @patch("api.hengpan.fetcher.query_kline")
    def test_resolve_scan_date_uses_selected_market_stocks_for_minute_data(self, query):
        query.side_effect = [
            pd.DataFrame(),
            pd.DataFrame([
                {"date": "2026-09-24", "time": "20260924150000000"},
                {"date": "2026-09-25", "time": "20260925103000000"},
            ]),
        ]

        self.assertEqual(
            resolve_scan_date(frequency="60", probe_codes=["sz.300001", "sz.300750"]),
            "2026-09-25",
        )
        self.assertEqual([call.args[0] for call in query.call_args_list], ["sz.300001", "sz.300750"])
        self.assertTrue(all(call.kwargs["frequency"] == "60" for call in query.call_args_list))

    def test_history_round_trip_preserves_frequency_and_old_defaults_to_daily(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(history, "_BASE_DIR", directory):
            history.save_history("minute", {
                "frequency": "60", "params": {"frequency": "60"}, "results": [],
                "stats": {"rules": {}},
            })
            self.assertEqual(history.get_history("minute")["frequency"], "60")
            self.assertEqual(history.list_histories()[0]["frequency"], "60")

            history.save_history("legacy", {"params": {}, "results": [], "stats": {"rules": {}}})
            self.assertEqual(history.get_history("legacy")["frequency"], "d")


if __name__ == "__main__":
    unittest.main()
