"""均线走平：纯算法、双市场参数和动态窗口的回归测试。"""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi import HTTPException
from pydantic import ValidationError

from api.hengpan import ma_flat, scanner
from api.hengpan.anchored_box import extract_series
from api.hengpan.router import HengpanMatch, HengpanRule, HengpanScanRequest, _rule_key, validate_rules
from api.crypto.hengpan_router import CryptoHengpanMatch, CryptoHengpanScanRequest
from api.crypto import hengpan_scan
from api.history.store import rule_keys


def bars(closes, end="2026-09-28 15:00:00"):
    closes = np.asarray(closes, dtype=float)
    count = len(closes)
    dates = pd.date_range(end=end, periods=count, freq="h")
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d %H:%M:%S"),
        "open_time": dates.tz_localize("Asia/Shanghai").asi8 // 1_000_000,
        "open": closes, "high": closes * 1.001, "low": closes * 0.999,
        "close": closes, "volume": np.ones(count) * 10,
        "amount": np.arange(count, dtype=float) + 100,
        "quote_asset_volume": np.arange(count, dtype=float) + 100,
        "number_of_trades": np.arange(count, dtype=float) + 10,
        "turn": np.ones(count), "isST": ["0"] * count,
    })


def params(**overrides):
    return {**HengpanRule().model_dump(), "box_type": "ma_flat", "ma_period": 30,
            "min_flat_bars": 30, "ma_tolerance": 0.01, "max_efficiency_ratio": 0.5,
            **overrides}


def check(closes, **overrides):
    return scanner.evaluate_rule(extract_series(bars(closes)), params(**overrides))


class MaFlatAlgorithmTest(unittest.TestCase):
    def test_constant_prices_have_longest_tail_and_zero_efficiency(self):
        result = check([100] * 120)
        self.assertEqual(result["mode"], "ma_flat")
        self.assertEqual(result["ma_period"], 30)
        self.assertEqual(result["flat_bars"], 91)
        self.assertEqual(result["ma_range"], 0)
        self.assertEqual(result["efficiency_ratio"], 0)
        self.assertTrue(result["history_limited"])
        self.assertTrue(result["passed_full"])
        self.assertEqual(result["passed_full"], result["passed_body"])
        self.assertAlmostEqual(result["avg_amount"], np.mean(np.arange(29, 120) + 100))

    def test_period_and_minimum_are_independent(self):
        result = check([100] * 60, ma_period=20, min_flat_bars=35)
        self.assertEqual(result["ma_period"], 20)
        self.assertEqual(result["flat_bars"], 41)
        self.assertTrue(result["passed_body"])

    def test_warmup_is_required_and_not_counted_as_flat_bars(self):
        self.assertIsNone(check([100] * 58))
        self.assertEqual(check([100] * 59)["flat_bars"], 30)
        self.assertIsNone(check([100] * 48, ma_period=20))
        self.assertEqual(check([100] * 49, ma_period=20)["flat_bars"], 30)

    def test_wide_oscillation_is_not_filtered_by_price_box_width(self):
        closes = 100 + 10 * np.sin(np.arange(300) * 2 * np.pi / 30)
        result = check(closes, box_height=0, max_breach=0, lookback=10)
        self.assertTrue(result["passed_full"])
        self.assertEqual(result["flat_bars"], 271)
        self.assertGreater(result["actual_range"], 0.2)

    def test_ma_range_finds_boundary_instead_of_using_fixed_lookback(self):
        closes = np.concatenate([np.linspace(60, 99, 100), np.full(100, 100)])
        result = check(closes, ma_tolerance=0)
        self.assertEqual(result["flat_bars"], 71)
        self.assertFalse(result["history_limited"])
        self.assertEqual(result["lookback_start"], bars(closes).iloc[-71]["date"])

    def test_slow_monotonic_trend_fails_efficiency_filter(self):
        closes = 100 + np.arange(200) * 0.01
        result = check(closes)
        self.assertGreaterEqual(result["flat_bars"], 30)
        self.assertAlmostEqual(result["efficiency_ratio"], 1)
        self.assertFalse(result["passed_body"])
        self.assertTrue(check(closes, max_efficiency_ratio=1)["passed_body"])

    def test_not_enough_flat_points_is_rejected_not_insufficient_history(self):
        result = check(np.arange(100, 200, dtype=float))
        self.assertIsNotNone(result)
        self.assertLess(result["flat_bars"], 30)
        self.assertFalse(result["passed_body"])

    def test_price_rescaling_does_not_change_result(self):
        closes = 100 + 2 * np.sin(np.arange(120) * 2 * np.pi / 17)
        reference = check(closes)
        for scale in (1e-7, 10000):
            result = check(closes * scale)
            self.assertEqual(result["flat_bars"], reference["flat_bars"])
            self.assertEqual(result["passed_body"], reference["passed_body"])
            self.assertAlmostEqual(result["ma_range"], reference["ma_range"], places=10)
            self.assertAlmostEqual(result["efficiency_ratio"], reference["efficiency_ratio"], places=10)

    def test_breakout_is_reported_but_is_not_an_extra_hard_filter(self):
        closes = np.full(120, 100.0)
        closes[-1] = 110
        result = check(closes, max_efficiency_ratio=1)
        self.assertTrue(result["passed_full"])
        self.assertEqual(result["tail_state"], "above")
        self.assertEqual(result["tail_bars"], 1)
        self.assertGreater(result["price_ma_distance"], 0.09)
        closes[-1] = 90
        self.assertEqual(check(closes, max_efficiency_ratio=1)["tail_state"], "below")

    def test_three_tail_bars_do_not_expand_the_breakout_reference(self):
        closes = [100] * 120 + [102] * 3
        result = check(closes, max_efficiency_ratio=1)
        self.assertTrue(result["passed_body"])
        self.assertEqual(result["tail_state"], "above")
        self.assertEqual(result["tail_bars"], 3)

    def test_invalid_prices_do_not_get_bridged_into_a_flat_segment(self):
        for invalid in (float("nan"), float("inf"), 0, -1):
            with self.subTest(invalid=invalid):
                closes = [100] * 100
                closes[-20] = invalid
                self.assertIsNone(check(closes))
                closes = [100] * 150
                closes[10] = invalid
                self.assertEqual(check(closes)["flat_bars"], 110)


class MaFlatContractTest(unittest.TestCase):
    def test_both_market_requests_accept_defaults(self):
        for model in (HengpanScanRequest, CryptoHengpanScanRequest):
            rule = model(rules=[{"box_type": "ma_flat"}]).rules[0]
            self.assertEqual(rule.ma_period, 30)
            self.assertEqual(rule.min_flat_bars, 30)
            self.assertEqual(rule.ma_tolerance, 0.01)
            self.assertEqual(rule.max_efficiency_ratio, 0.5)

    def test_invalid_parameters_are_rejected(self):
        bad = {"ma_period": [1, 30.5, 501], "min_flat_bars": [1, 30.5, 1001],
               "ma_tolerance": [-0.01, float("nan"), float("inf")],
               "max_efficiency_ratio": [-0.1, 1.01, float("nan")]}
        for key, values in bad.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                    HengpanRule(**params(**{key: value}))

    def test_duplicate_key_uses_only_active_mode_parameters(self):
        rule = params()
        irrelevant = {**rule, "lookback": 10, "max_breach": 20, "box_height": 0.9}
        self.assertEqual(_rule_key(rule), _rule_key(irrelevant))
        for key, value in {"ma_period": 20, "min_flat_bars": 40, "ma_tolerance": 0.02,
                           "max_efficiency_ratio": 0.3}.items():
            self.assertNotEqual(_rule_key(rule), _rule_key({**rule, key: value}))
        self.assertEqual(len(validate_rules([irrelevant])), 1)
        with self.assertRaises(HTTPException):
            validate_rules([rule, irrelevant])

    def test_match_metrics_survive_both_response_models(self):
        result = check([100] * 120)
        for model in (HengpanMatch, CryptoHengpanMatch):
            saved = model(**result).model_dump()
            for key in ("ma_period", "flat_bars", "ma_range", "efficiency_ratio", "ma_value",
                        "price_ma_distance", "tail_state", "tail_bars", "history_limited"):
                self.assertEqual(saved[key], result[key])

    def test_history_rule_identity_distinguishes_ma_period_but_ignores_old_fields(self):
        def keys(rule):
            return rule_keys({"kind": "hengpan_a", "frequency": "60", "rules": [{"id": "1", "params": rule}]},
                             {"matched_rules": ["1"]})
        self.assertNotEqual(keys(params()), keys(params(ma_period=20)))
        self.assertEqual(keys(params()), keys(params(lookback=40, max_breach=10)))


class MaFlatDataTest(unittest.TestCase):
    def test_crypto_uses_close_time_not_open_time(self):
        frame = bars([100] * 60, end="2026-09-28 12:00:00")
        selected = ma_flat.closed_frame(frame, "1h", now="2026-09-28 12:30:00+08:00")
        self.assertEqual(selected.iloc[-1]["date"], "2026-09-28 11:00:00")
        self.assertEqual(len(selected), 59)

    def test_stock_minute_timestamps_are_bar_end_times(self):
        frame = bars([100] * 60, end="2026-09-28 15:00:00")
        selected = ma_flat.closed_frame(frame, "60", now="2026-09-28 14:30:00+08:00")
        self.assertEqual(selected.iloc[-1]["date"], "2026-09-28 14:00:00")

    def test_unfinished_daily_bar_is_excluded(self):
        frame = bars([100] * 3)
        frame["date"] = ["2026-09-24", "2026-09-25", "2026-09-28"]
        selected = ma_flat.closed_frame(frame, "d", now="2026-09-28 14:30:00+08:00")
        self.assertEqual(len(selected), 2)
        self.assertEqual(len(ma_flat.closed_frame(frame, "d", now="2026-09-28 15:00:00+08:00")), 3)

    def test_stock_session_breaks_are_not_missing_bars(self):
        calendar = ["2026-09-25", "2026-09-28"]
        frame = bars([100] * 8)
        frame["date"] = [f"{day} {time}" for day in calendar
                         for time in ("10:30:00", "11:30:00", "14:00:00", "15:00:00")]
        self.assertEqual(len(ma_flat.continuous_frame(frame, "60", calendar)), 8)
        missing = frame.drop(index=2).reset_index(drop=True)
        tail = ma_flat.continuous_frame(missing, "60", calendar)
        self.assertEqual(len(tail), 5)
        self.assertTrue(tail.attrs["continuity_gap"])

    def test_stock_calendar_gap_truncates_only_the_old_segment(self):
        calendar = pd.bdate_range("2026-06-01", periods=90).strftime("%Y-%m-%d").tolist()
        frame = bars([100] * 90)
        frame["date"] = calendar
        frame = frame.drop(index=20).reset_index(drop=True)
        tail = ma_flat.continuous_frame(frame, "d", calendar)
        self.assertEqual(len(tail), 69)
        self.assertTrue(tail.attrs["continuity_gap"])

    def test_crypto_fetches_all_stored_history_for_ma_mode(self):
        frame = bars([100] * 800)
        rules = [{"id": "1", "params": params()}]
        stats = hengpan_scan.new_stats("2026-09-28", rules)
        with patch.object(hengpan_scan, "load_frames", return_value={"TESTUSDT": frame}) as load, \
                patch.object(hengpan_scan, "latest_scan_timestamp", return_value="2026-09-28"):
            items = hengpan_scan.scan_hengpan(None, [{"symbol": "TESTUSDT", "category": "perpetual"}],
                                               rules, "2026-09-28", stats)
        self.assertIsNone(load.call_args.args[2])
        self.assertEqual(items[0]["matches"]["1"]["flat_bars"], 771)


class MaFlatIntegrationTest(unittest.TestCase):
    def test_both_scanners_use_dynamic_window_for_metrics(self):
        frame = bars([100] * 200)
        rules = [{"id": "1", "params": params(ma_period=20)}]
        a_stats = scanner.new_stats("2026-09-28", rules)
        a = scanner.analyze_stock({"code": "sh.600000", "name": "测试", "industry": "测试"},
                                 frame, rules, "2026-09-28", a_stats)
        u_stats = hengpan_scan.new_stats("2026-09-28", rules)
        u = hengpan_scan.analyze_symbol({"symbol": "TESTUSDT", "category": "perpetual"},
                                       frame, rules, "2026-09-28", u_stats)
        self.assertEqual(a["matches"]["1"]["flat_bars"], 181)
        self.assertEqual(u["matches"]["1"]["flat_bars"], 181)
        self.assertAlmostEqual(u["matches"]["1"]["avg_trades"], np.mean(np.arange(19, 200) + 10))

    def test_crypto_gap_truncates_history_without_rejecting_a_later_valid_platform(self):
        frame = bars([100] * 200).drop(index=50).reset_index(drop=True)
        rules = [{"id": "1", "params": params()}]
        stats = hengpan_scan.new_stats("2026-09-28", rules)
        item = hengpan_scan.analyze_symbol({"symbol": "TESTUSDT", "category": "perpetual"},
                                          frame, rules, "2026-09-28", stats)
        self.assertIsNotNone(item)
        self.assertEqual(item["matches"]["1"]["flat_bars"], 120)
        self.assertTrue(item["matches"]["1"]["history_limited"])

    def test_crypto_gap_in_ma_warmup_excludes_the_rule(self):
        frame = bars([100] * 120).drop(index=70).reset_index(drop=True)
        rules = [{"id": "1", "params": params()}]
        stats = hengpan_scan.new_stats("2026-09-28", rules)
        item = hengpan_scan.analyze_symbol({"symbol": "TESTUSDT", "category": "perpetual"},
                                          frame, rules, "2026-09-28", stats)
        self.assertIsNone(item)
        self.assertEqual(stats["skipped"]["gap"], 1)


if __name__ == "__main__":
    unittest.main()
