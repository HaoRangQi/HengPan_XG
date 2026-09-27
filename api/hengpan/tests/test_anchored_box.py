"""
末端锚定横盘箱体的单元测试，用例来自方案文档第 12.1 节和 V2.0 的推导 7。
在项目根目录运行：api/.venv/bin/python -m unittest api.hengpan.tests.test_anchored_box -v
"""
import unittest

import pandas as pd

from api.hengpan.anchored_box import LOOKBACK, check_anchored_box, check_series, extract_series


def bar(high, low, close, open_=None):
    """一根 K 线；不给开盘价时开盘等于收盘。"""
    return {"open": close if open_ is None else open_, "high": high, "low": low, "close": close}


def reference_hist():
    """参考箱体（V2.0 第 6.1 节）：80 根都在 [9.70, 10.00] 内，其中 6 根最高价摸到 10.00，5 根最低价探到 9.70。"""
    rows = [bar(9.90, 9.80, 9.86, 9.84) for _ in range(LOOKBACK)]
    for i in range(0, 60, 10):
        rows[i]["high"] = 10.00
    for i in range(5, 55, 10):
        rows[i]["low"] = 9.70
    return rows


def make_df(hist_rows, last):
    """回验区间加末端 K 线拼成日线表，日期、成交额、换手率填固定值。"""
    df = pd.DataFrame([dict(row) for row in hist_rows] + [last])
    df["date"] = pd.bdate_range("2026-01-05", periods=len(df)).strftime("%Y-%m-%d")
    df["amount"] = 1e8
    df["turn"] = 1.5
    return df


DOJI_TOP = bar(10.02, 9.98, 10.00, 9.99)   # 振幅 0.4%，中点 10.00 正好贴着箱顶


class AnchoredBoxTest(unittest.TestCase):
    def check(self, last, hist=None, **kwargs):
        return check_anchored_box(make_df(hist or reference_hist(), last), **kwargs)

    def test_doji_at_box_top_passes(self):
        result = self.check(DOJI_TOP)
        self.assertEqual(result["mode"], "doji")
        self.assertAlmostEqual(result["upper"], 10.00)
        self.assertAlmostEqual(result["lower"], 9.60)
        # 6 根最高价恰好等于上轨算箱内；末端自己的最高价 10.02 高过上轨，但不参与回验
        self.assertEqual(result["breach_full"], 0)
        self.assertTrue(result["passed_full"])

    def test_normal_bar_in_box_middle_passes(self):
        result = self.check(bar(9.95, 9.75, 9.90, 9.80))
        self.assertEqual(result["mode"], "normal")
        self.assertAlmostEqual(result["upper"], 9.85 * 1.02)
        self.assertAlmostEqual(result["lower"], 9.85 * 0.98)
        self.assertTrue(result["passed_full"])

    def test_doji_at_box_bottom_fails(self):
        result = self.check(bar(9.73, 9.71, 9.72))
        self.assertEqual(result["mode"], "doji")
        self.assertEqual(result["breach_full"], LOOKBACK)
        self.assertFalse(result["passed_full"])

    def test_one_price_limit_up_fails(self):
        result = self.check(bar(10.85, 10.85, 10.85))
        self.assertEqual(result["mode"], "doji")
        self.assertEqual(result["breach_full"], LOOKBACK)
        self.assertFalse(result["passed_body"])

    def test_breakdown_bar_fails(self):
        result = self.check(bar(9.40, 9.20, 9.22, 9.40))
        self.assertEqual(result["mode"], "normal")
        self.assertEqual(result["breach_full"], LOOKBACK)
        self.assertFalse(result["passed_full"])

    def test_doji_range_above_box_top(self):
        # 十字星中点只能落在 [hi, lo / 0.96] = [10.00, 10.104]
        self.assertTrue(self.check(bar(10.12, 10.08, 10.10))["passed_full"])
        result = self.check(bar(10.13, 10.09, 10.11))
        self.assertEqual(result["breach_full"], 5)  # 下轨 9.7056 高过 5 根 9.70 的最低价
        self.assertFalse(result["passed_full"])

    def test_normal_bar_off_center_fails(self):
        # 普通 K 线中点只能落在 [10.00 / 1.02, 9.70 / 0.98] = [9.804, 9.898]
        result = self.check(bar(9.90, 9.70, 9.80))  # 中点 9.80，上轨 9.996
        self.assertEqual(result["mode"], "normal")
        self.assertEqual((result["breach_full"], result["breach_body"]), (6, 0))
        self.assertFalse(result["passed_full"])

    def test_two_wick_breaches_pass_three_fail(self):
        hist = reference_hist()
        for i in (1, 2):  # 长上影线：最高价 10.30 越界，实体 9.95 ~ 9.98 在箱内
            hist[i] = bar(10.30, 9.80, 9.98, 9.95)
        result = self.check(DOJI_TOP, hist)
        self.assertEqual((result["breach_full"], result["breach_body"]), (2, 0))
        self.assertTrue(result["passed_full"])

        hist[3] = bar(10.30, 9.80, 9.98, 9.95)
        result = self.check(DOJI_TOP, hist)
        self.assertEqual((result["breach_full"], result["breach_body"]), (3, 0))
        self.assertFalse(result["passed_full"])
        self.assertTrue(result["passed_body"])

    def test_amplitude_exactly_half_percent_is_doji(self):
        self.assertEqual(self.check(bar(10.025, 9.975, 10.00))["mode"], "doji")

    def test_insufficient_data_returns_none(self):
        df = make_df(reference_hist()[1:], DOJI_TOP)  # 只有 80 根
        self.assertIsNone(check_anchored_box(df))

    def test_forced_mode_for_boundary_stats(self):
        result = self.check(DOJI_TOP, mode="normal")  # 同一根 K 线按普通模式锚定：下轨 9.80
        self.assertEqual(result["mode"], "normal")
        self.assertEqual(result["breach_full"], 5)
        self.assertFalse(result["passed_full"])

    def test_outputs_liquidity_and_lookback_start(self):
        df = make_df(reference_hist(), DOJI_TOP)
        result = check_anchored_box(df)
        self.assertAlmostEqual(result["avg_amount"], 1e8)
        self.assertAlmostEqual(result["avg_turn"], 1.5)
        self.assertEqual(result["lookback_start"], df["date"].iloc[0])

    def test_outputs_actual_range_for_lookback_and_terminal_bar(self):
        df = make_df(reference_hist(), DOJI_TOP)
        result = check_anchored_box(df)
        expected = (10.02 - 9.70) / 9.70
        self.assertAlmostEqual(result["actual_range"], expected)

    def test_custom_lookback(self):
        df = make_df(reference_hist()[-10:], DOJI_TOP)  # 10 根回验 + 末端
        self.assertIsNone(check_anchored_box(df))
        result = check_anchored_box(df, lookback=10)
        self.assertEqual(result["lookback_start"], df["date"].iloc[0])
        self.assertTrue(result["passed_full"])


class MultiRuleTest(unittest.TestCase):
    """一次取数按多组规则各算一遍：结果必须和逐组单算完全一致。"""

    RULES = [
        {"box_height": 0.04, "lookback": 80, "max_breach": 2},
        {"box_height": 0.08, "lookback": 40, "max_breach": 2},
        {"box_height": 0.04, "lookback": 200, "max_breach": 2},  # 数据不够，这组应返回 None
    ]

    def test_shared_series_matches_per_rule_calls(self):
        df = make_df(reference_hist(), DOJI_TOP)
        series = extract_series(df)
        for rule in self.RULES:
            self.assertEqual(check_series(series, **rule), check_anchored_box(df, **rule))

    def test_rules_are_independent(self):
        # 末端十字星中点 10.00：箱高 4% 时下轨 9.60，5 根 9.70 的最低价都在箱内
        df = make_df(reference_hist(), DOJI_TOP)
        series = extract_series(df)
        self.assertTrue(check_series(series, **self.RULES[0])["passed_full"])
        # 同一份数据、同一根末端 K 线，换一组规则只影响这一组的判定
        loose = check_series(series, **self.RULES[1])
        self.assertTrue(loose["passed_full"])
        self.assertAlmostEqual(loose["lower"], 10.00 * 0.92)
        self.assertIsNone(check_series(series, **self.RULES[2]))

    def test_lookback_changes_window_and_averages(self):
        hist = reference_hist()
        hist[0] = bar(12.00, 9.80, 9.86, 9.84)  # 最早那根远高于箱体，只有长回验才会看到它
        df = make_df(hist, DOJI_TOP)
        series = extract_series(df)
        self.assertEqual(check_series(series, lookback=80)["breach_full"], 1)
        self.assertEqual(check_series(series, lookback=40)["breach_full"], 0)
        self.assertEqual(check_series(series, lookback=40)["lookback_start"], df["date"].iloc[40])


if __name__ == "__main__":
    unittest.main()
