"""
停牌缺口的单元测试：回验窗口里缺了交易日，这组规则不判定。
在项目根目录运行：api/.venv/bin/python -m unittest api.hengpan.tests.test_suspension -v
"""
import unittest

from api.hengpan.router import HengpanRule
from api.hengpan.scanner import analyze_stock, new_stats, window_has_gap
from api.hengpan.tests.test_anchored_box import bar, make_df, reference_hist

STOCK = {"code": "sh.600000", "name": "测试", "industry": "银行"}
# 末端振幅正好 0.5%、中点 10.00，按默认规则能以十字星模式入选（见 test_amplitude_mode）
LAST_BAR = bar(10.025, 9.975, 10.00)
EXTRA = 10   # 回验区间前面多垫几根，删掉一根之后仍够 lookback + 1


def build(drop=None):
    """默认规则能入选的日线表，外加完整的交易日历；drop 给出要删掉的行号，模拟那天停牌。"""
    hist = [bar(9.90, 9.80, 9.86, 9.84) for _ in range(EXTRA)] + reference_hist()
    df = make_df(hist, LAST_BAR)
    df["volume"] = 1e6
    df["isST"] = "0"
    trading_days = df["date"].tolist()
    if drop is not None:
        df = df.drop(index=drop).reset_index(drop=True)
    return df, trading_days


def rules_with(*lookbacks):
    base = HengpanRule().model_dump()
    return [{"id": str(i + 1), "params": {**base, "lookback": lookback}}
            for i, lookback in enumerate(lookbacks)]


class WindowHasGapTest(unittest.TestCase):
    def test_continuous_window_has_no_gap(self):
        df, days = build()
        self.assertFalse(window_has_gap(df["date"].to_numpy(), 80, days))

    def test_missing_day_inside_window_is_a_gap(self):
        df, days = build(drop=50)
        self.assertTrue(window_has_gap(df["date"].to_numpy(), 80, days))

    def test_missing_day_before_window_is_ignored(self):
        """停牌发生在回验窗口之前，不影响这组规则。"""
        df, days = build(drop=2)
        self.assertFalse(window_has_gap(df["date"].to_numpy(), 80, days))

    def test_minute_bars_use_the_date_part(self):
        dates = ["2026-09-23 10:30:00", "2026-09-23 15:00:00",
                 "2026-09-25 10:30:00", "2026-09-25 15:00:00"]
        self.assertTrue(window_has_gap(dates, 3, ["2026-09-23", "2026-09-24", "2026-09-25"]))
        self.assertFalse(window_has_gap(dates, 3, ["2026-09-23", "2026-09-25"]))

    def test_without_calendar_nothing_is_flagged(self):
        df, _ = build(drop=50)
        self.assertFalse(window_has_gap(df["date"].to_numpy(), 80, None))
        self.assertFalse(window_has_gap(df["date"].to_numpy(), 80, []))


class AnalyzeStockSuspensionTest(unittest.TestCase):
    def test_continuous_stock_still_passes(self):
        df, days = build()
        rules = rules_with(80)
        stats = new_stats(df["date"].iloc[-1], rules)
        item = analyze_stock(STOCK, df, rules, df["date"].iloc[-1], stats, trading_days=days)
        self.assertEqual(list(item["matches"]), ["1"])
        self.assertEqual(stats["skipped"]["suspended"], 0)

    def test_suspension_inside_window_excludes_the_stock(self):
        """同一只本来能入选的股票，窗口里停牌一天就不判定，也不算「数据不足」。"""
        df, days = build(drop=50)
        rules = rules_with(80)
        stats = new_stats(df["date"].iloc[-1], rules)
        item = analyze_stock(STOCK, df, rules, df["date"].iloc[-1], stats, trading_days=days)
        self.assertIsNone(item)
        self.assertEqual(stats["skipped"]["suspended"], 1)
        self.assertEqual(stats["skipped"]["insufficient"], 0)
        self.assertEqual(stats["rules"]["1"]["suspended"], 1)
        self.assertEqual(stats["rules"]["1"]["analyzed"], 0)

    def test_each_rule_checks_its_own_window(self):
        """停牌只落在长窗口里：长回验的规则不判定，短回验的规则照常判定。"""
        df, days = build(drop=50)
        rules = rules_with(80, 20)
        stats = new_stats(df["date"].iloc[-1], rules)
        analyze_stock(STOCK, df, rules, df["date"].iloc[-1], stats, trading_days=days)
        self.assertEqual((stats["rules"]["1"]["suspended"], stats["rules"]["1"]["analyzed"]), (1, 0))
        self.assertEqual((stats["rules"]["2"]["suspended"], stats["rules"]["2"]["analyzed"]), (0, 1))
        self.assertEqual(stats["skipped"]["suspended"], 0)   # 还有规则判定了，不算整只跳过

    def test_without_calendar_behaviour_is_unchanged(self):
        """没有交易日历时不检查缺口，和改动前的行为一致。"""
        df, _ = build(drop=50)
        rules = rules_with(80)
        stats = new_stats(df["date"].iloc[-1], rules)
        analyze_stock(STOCK, df, rules, df["date"].iloc[-1], stats)
        self.assertEqual(stats["skipped"]["suspended"], 0)
        self.assertEqual(stats["rules"]["1"]["analyzed"], 1)


if __name__ == "__main__":
    unittest.main()
