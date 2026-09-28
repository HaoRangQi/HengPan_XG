import unittest

import numpy as np
from pydantic import ValidationError

from api.hengpan.router import HengpanRule, HengpanScanRequest, _rule_key
from api.hengpan.scanner import evaluate_rule
from api.hengpan.tolerant_box import check_tolerant_series


def series(rows):
    result = {key: np.array([row[key] for row in rows], dtype=float)
              for key in ("open", "high", "low", "close")}
    result.update({
        "date": np.array([f"2026-01-{index + 1:02d}" for index in range(len(rows))]),
        "amount": np.full(len(rows), 1e8),
        "turn": np.full(len(rows), 1.5),
    })
    return result


def candle(center=10.0, body=0.02, high=None, low=None):
    open_ = center - body / 2
    close = center + body / 2
    return {
        "open": open_, "close": close,
        "high": high if high is not None else close + 0.02,
        "low": low if low is not None else open_ - 0.02,
    }


class TolerantBoxTest(unittest.TestCase):
    def test_finds_four_percent_box_covering_most_entity_centers(self):
        rows = [candle(10 + (index % 5) * 0.05) for index in range(80)]
        result = check_tolerant_series(series(rows), lookback=80, box_height=0.04,
                                       max_breach=4, max_consecutive_breach=1)
        self.assertEqual(result["mode"], "tolerant")
        self.assertEqual(result["breach_body"], 0)
        self.assertTrue(result["passed_full"])
        self.assertTrue(result["passed_body"])
        self.assertLessEqual((result["upper"] - result["lower"]) / result["lower"], 0.04 + 1e-9)

    def test_long_wicks_do_not_move_box_or_fail_default_result(self):
        rows = [candle(10.0) for _ in range(80)]
        rows[10] = candle(10.0, high=13.0, low=9.98)
        result = check_tolerant_series(series(rows), lookback=80)
        self.assertEqual(result["breach_body"], 0)
        self.assertEqual(result["breach_full"], 1)
        self.assertTrue(result["passed_full"])

    def test_four_isolated_entity_spikes_pass(self):
        rows = [candle(10.0) for _ in range(80)]
        for index in (5, 20, 40, 60):
            rows[index] = candle(10.8)
        result = check_tolerant_series(series(rows), lookback=80, max_breach=4,
                                       max_consecutive_breach=1)
        self.assertEqual(result["breach_body"], 4)
        self.assertEqual(result["longest_consecutive_breach"], 1)
        self.assertTrue(result["passed_body"])

    def test_two_consecutive_entity_spikes_fail(self):
        rows = [candle(10.0) for _ in range(80)]
        rows[20] = candle(10.8)
        rows[21] = candle(10.8)
        result = check_tolerant_series(series(rows), lookback=80, max_breach=4,
                                       max_consecutive_breach=1)
        self.assertEqual(result["breach_body"], 2)
        self.assertEqual(result["longest_consecutive_breach"], 2)
        self.assertFalse(result["passed_body"])

    def test_large_body_crossing_a_rail_counts_as_spike_even_when_center_is_inside(self):
        rows = [candle(10.0) for _ in range(80)]
        rows[12] = candle(10.0, body=1.0)
        result = check_tolerant_series(series(rows), lookback=80, max_breach=0)
        self.assertEqual(result["breach_body"], 1)
        self.assertFalse(result["passed_body"])

    def test_prices_equal_to_rails_are_inside(self):
        rows = [candle(10.0, body=0.0) for _ in range(80)]
        result = check_tolerant_series(series(rows), lookback=80, box_height=0,
                                       max_breach=0)
        self.assertEqual((result["lower"], result["upper"]), (10.0, 10.0))
        self.assertEqual(result["breach_body"], 0)
        self.assertTrue(result["passed_body"])

    def test_insufficient_data_returns_none(self):
        self.assertIsNone(check_tolerant_series(series([candle(10.0) for _ in range(79)]), lookback=80))


class TolerantRuleContractTest(unittest.TestCase):
    def test_request_accepts_tolerant_mode_defaults(self):
        rule = HengpanScanRequest(rules=[{"box_type": "tolerant"}]).rules[0]
        self.assertEqual(rule.box_type, "tolerant")
        self.assertEqual(rule.max_consecutive_breach, 1)

    def test_consecutive_limit_is_validated(self):
        with self.assertRaises(ValidationError):
            HengpanScanRequest(rules=[{"box_type": "tolerant", "max_consecutive_breach": 0}])

    def test_duplicate_key_uses_only_tolerant_fields(self):
        rule = {**HengpanRule().model_dump(), "box_type": "tolerant", "max_breach": 4}
        self.assertEqual(_rule_key(rule), _rule_key({**rule, "doji_amplitude": 0.02, "amp_multiple": 9}))
        self.assertNotEqual(_rule_key(rule), _rule_key({**rule, "max_consecutive_breach": 2}))

    def test_scanner_dispatches_tolerant_rule_without_passing_legacy_only_fields(self):
        rows = [candle(10.0) for _ in range(80)]
        params = {**HengpanRule(box_type="tolerant", max_breach=4).model_dump()}
        result = evaluate_rule(series(rows), params)
        self.assertEqual(result["mode"], "tolerant")
        self.assertTrue(result["passed_body"])


if __name__ == "__main__":
    unittest.main()
