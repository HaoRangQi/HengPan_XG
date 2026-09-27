"""
振幅模式的单元测试：箱体 = 末端 K 线最高价往上、最低价往下各延伸 k 倍末端振幅，不区分十字星。
在项目根目录运行：api/.venv/bin/python -m unittest api.hengpan.tests.test_amplitude_mode -v
"""
import unittest

from pydantic import ValidationError

from api.hengpan.anchored_box import LOOKBACK, check_anchored_box, check_series, extract_series
from api.hengpan.router import HengpanRule, HengpanScanRequest, _rule_key
from api.hengpan.scanner import analyze_stock, new_stats
from api.hengpan.tests.test_anchored_box import DOJI_TOP, bar, make_df, reference_hist

MIDDLE_BAR = bar(9.95, 9.75, 9.90, 9.80)   # 振幅 0.20，在参考箱体 [9.70, 10.00] 中部


class AmplitudeBoxTest(unittest.TestCase):
    def check(self, last, **kwargs):
        return check_anchored_box(make_df(reference_hist(), last), box_type="amplitude", **kwargs)

    def test_default_extends_one_range_each_side(self):
        result = self.check(MIDDLE_BAR)  # 箱体 [9.75 - 0.20, 9.95 + 0.20]
        self.assertEqual(result["mode"], "amplitude")
        self.assertAlmostEqual(result["upper"], 10.15)
        self.assertAlmostEqual(result["lower"], 9.55)
        self.assertEqual(result["breach_full"], 0)
        self.assertTrue(result["passed_full"])

    def test_multiple_scales_the_box(self):
        result = self.check(MIDDLE_BAR, amp_multiple=0.2)  # 箱体 [9.71, 9.99]
        self.assertAlmostEqual(result["upper"], 9.99)
        self.assertAlmostEqual(result["lower"], 9.71)
        self.assertEqual(result["breach_full"], 11)  # 6 根最高价 10.00、5 根最低价 9.70
        self.assertFalse(result["passed_full"])

    def test_doji_gets_no_special_anchor(self):
        result = self.check(DOJI_TOP)  # 振幅 0.04，箱体 [9.94, 10.06]
        self.assertEqual(result["mode"], "amplitude")
        self.assertAlmostEqual(result["upper"], 10.06)
        self.assertAlmostEqual(result["lower"], 9.94)
        self.assertEqual(result["breach_full"], LOOKBACK)  # 80 根最低价都不高于 9.80
        self.assertFalse(result["passed_full"])

    def test_zero_range_bar_fails(self):
        result = self.check(bar(10.85, 10.85, 10.85))
        self.assertAlmostEqual(result["upper"], result["lower"])
        self.assertEqual(result["breach_full"], LOOKBACK)

    def test_large_last_bar_box_covers_history(self):
        # 末端大阳线振幅 0.43，箱体 [9.59, 10.88]，参考箱体 80 根全在里面：振幅模式下这种情况会入选
        result = self.check(bar(10.45, 10.02, 10.40, 10.05))
        self.assertAlmostEqual(result["upper"], 10.88)
        self.assertAlmostEqual(result["lower"], 9.59)
        self.assertTrue(result["passed_full"])

    def test_lower_bound_is_not_negative(self):
        result = self.check(bar(12.00, 6.00, 9.00), amp_multiple=2)
        self.assertAlmostEqual(result["upper"], 24.00)
        self.assertEqual(result["lower"], 0.0)

    def test_unknown_box_type_is_rejected(self):
        with self.assertRaises(ValueError):
            check_anchored_box(make_df(reference_hist(), DOJI_TOP), box_type="other")

    def test_fixed_and_amplitude_rules_share_one_series(self):
        series = extract_series(make_df(reference_hist(), DOJI_TOP))
        fixed = check_series(series)
        amplitude = check_series(series, box_type="amplitude")
        self.assertEqual((fixed["mode"], fixed["passed_full"]), ("doji", True))
        self.assertEqual((amplitude["mode"], amplitude["passed_full"]), ("amplitude", False))


class ScannerStatsTest(unittest.TestCase):
    """扫描统计：十字星分界只统计固定箱高的规则组，振幅模式的组不计入。"""

    def test_boundary_stats_skip_amplitude_rules(self):
        df = make_df(reference_hist(), bar(10.025, 9.975, 10.00))  # 振幅正好 0.5%，中点 10.00
        df["volume"] = 1e6
        df["isST"] = "0"
        scan_date = df["date"].iloc[-1]
        base = HengpanRule().model_dump()
        rules = [{"id": "1", "params": base},
                 {"id": "2", "params": {**base, "box_type": "amplitude"}}]
        stats = new_stats(scan_date, rules)

        item = analyze_stock({"code": "sh.600000", "name": "测试", "industry": "银行"}, df, rules, scan_date, stats)

        self.assertEqual(list(item["matches"]), ["1"])  # 振幅模式箱体 [9.925, 10.075]，80 根最低价都越界
        self.assertEqual(item["matches"]["1"]["mode"], "doji")
        self.assertEqual((stats["rules"]["1"]["near"], stats["rules"]["2"]["near"]), (1, 0))
        self.assertEqual((stats["rules"]["1"]["passed_full"], stats["rules"]["2"]["passed_full"]), (1, 0))


class RuleRequestTest(unittest.TestCase):
    def test_defaults_keep_fixed_box(self):
        rule = HengpanScanRequest().rules[0]
        self.assertEqual((rule.box_type, rule.amp_multiple), ("fixed", 1.0))

    def test_amplitude_rule_is_accepted(self):
        rule = HengpanScanRequest(rules=[{"box_type": "amplitude", "amp_multiple": 1.5}]).rules[0]
        self.assertEqual((rule.box_type, rule.amp_multiple), ("amplitude", 1.5))

    def test_invalid_values_are_rejected(self):
        for bad in ({"box_type": "other"}, {"box_type": "amplitude", "amp_multiple": 0},
                    {"box_type": "amplitude", "amp_multiple": 21}):
            with self.subTest(rule=bad), self.assertRaises(ValidationError):
                HengpanScanRequest(rules=[bad])

    def test_duplicate_key_ignores_unused_params(self):
        base = HengpanRule().model_dump()
        amplitude = {**base, "box_type": "amplitude"}
        # 振幅模式不看十字星上限和箱高：只改这两项仍算重复
        self.assertEqual(_rule_key(amplitude), _rule_key({**amplitude, "doji_amplitude": 0.01, "box_height": 0.1}))
        self.assertNotEqual(_rule_key(amplitude), _rule_key({**amplitude, "amp_multiple": 2.0}))
        # 固定箱高不看振幅倍数
        self.assertEqual(_rule_key(base), _rule_key({**base, "amp_multiple": 3.0}))
        self.assertNotEqual(_rule_key(base), _rule_key(amplitude))


if __name__ == "__main__":
    unittest.main()
