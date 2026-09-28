"""横盘-U 扫描：缺口检测、回验窗口、末端判定和统计。"""
import unittest

import numpy as np
import pandas as pd

from api.crypto import db
from api.crypto.hengpan_scan import (
    INTERVAL_MS,
    beijing_day_end_ms,
    build_frame,
    fetch_range,
    lookback_window,
    analyze_symbol,
    new_stats,
    scan_hengpan,
    window_has_gap,
)
from api.hengpan.router import HengpanRule, validate_rules

SYMBOL = {"symbol": "BTCUSDT", "category": "perpetual", "baseAsset": "BTC",
          "quoteVolume": 5e8, "lastPrice": "100.5", "priceChangePercent": "0.3"}


def raw_bars(count=120, price=100.0, end="2026-09-28 23:00:00", step_hours=1):
    """一段横盘的 1 小时线，字段和 reader.load_kline 的输出一致。"""
    last = pd.Timestamp(end, tz="Asia/Shanghai")
    times = [last - pd.Timedelta(hours=step_hours * (count - 1 - index)) for index in range(count)]
    return pd.DataFrame({
        "category": ["perpetual"] * count,
        "date": [moment.strftime("%Y-%m-%d %H:%M:%S") for moment in times],
        "symbol": ["BTCUSDT"] * count,
        "open_time": [int(moment.value // 1_000_000) for moment in times],
        "open": np.full(count, price),
        "high": np.full(count, price * 1.002),
        "low": np.full(count, price * 0.998),
        "close": np.full(count, price),
        "volume": np.full(count, 10.0),
        "quote_asset_volume": np.full(count, 250_000.0),
        "number_of_trades": np.full(count, 1_800),
    })


def tolerant_rules(**overrides):
    params = {"box_type": "tolerant", "box_height": 0.04, "lookback": 80,
              "max_breach": 4, "max_consecutive_breach": 1}
    params.update(overrides)
    return validate_rules([HengpanRule(**params).model_dump()])


class CryptoHengpanGapTest(unittest.TestCase):
    def test_evenly_spaced_window_has_no_gap(self):
        times = [index * INTERVAL_MS for index in range(100)]
        self.assertFalse(window_has_gap(times, 80))
        self.assertFalse(window_has_gap(times, 80, anchored=False))

    def test_missing_bar_inside_window_is_a_gap(self):
        times = [index * INTERVAL_MS for index in range(100)]
        self.assertTrue(window_has_gap(times[:50] + times[51:], 80))

    def test_gap_outside_the_window_is_ignored(self):
        """缺口在回验窗口之前，这一组规则照常判定。"""
        times = [index * INTERVAL_MS for index in range(100)]
        self.assertFalse(window_has_gap(times[:5] + times[6:], 80))

    def test_too_few_bars_is_not_reported_as_gap(self):
        """根数不足由算法返回 None 来处理，不算缺口。"""
        self.assertFalse(window_has_gap([0, INTERVAL_MS], 80))


class CryptoHengpanWindowTest(unittest.TestCase):
    def test_anchored_window_excludes_the_last_bar(self):
        """末端锚定模式：回验区间是末端之前的 lookback 根。"""
        self.assertEqual(lookback_window("fixed", 80, 100), slice(19, 99))
        self.assertEqual(lookback_window("amplitude", 80, 100), slice(19, 99))

    def test_tolerant_window_includes_the_last_bar(self):
        self.assertEqual(lookback_window("tolerant", 80, 100), slice(20, 100))

    def test_fetch_range_covers_lookback_even_when_the_day_is_unfinished(self):
        """扫描日只走到上午时，窗口也要够取 lookback + 1 根。"""
        start_ms, end_ms = fetch_range("2026-09-28", 80)
        self.assertEqual(end_ms, beijing_day_end_ms("2026-09-28"))
        # 当天最新一根在 00:00 这种极端情况下，仍然剩下 80 根以上
        remaining = (end_ms - 86_400_000 - start_ms) // INTERVAL_MS
        self.assertGreater(remaining, 80)


class CryptoHengpanAnalyzeTest(unittest.TestCase):
    def test_flat_series_passes_and_reports_crypto_fields(self):
        frame = build_frame(raw_bars())
        stats = new_stats("2026-09-28", tolerant_rules())
        item = analyze_symbol(SYMBOL, frame, tolerant_rules(), "2026-09-28", stats)

        self.assertIsNotNone(item)
        self.assertEqual(item["symbol"], "BTCUSDT")
        self.assertEqual(item["base_asset"], "BTC")
        self.assertEqual(item["category_label"], db.CATEGORY_LABELS["perpetual"])
        self.assertEqual(item["quote_volume"], 5e8)
        match = item["matches"]["1"]
        # 成交额取 quote_asset_volume（USDT），换手率换成成交笔数
        self.assertAlmostEqual(match["avg_amount"], 250_000.0)
        self.assertAlmostEqual(match["avg_trades"], 1_800.0)
        self.assertIsNone(match["avg_turn"])
        self.assertEqual(stats["rules"]["1"]["passed_full"], 1)

    def test_bar_from_another_day_counts_as_stale(self):
        frame = build_frame(raw_bars(end="2026-09-26 23:00:00"))
        stats = new_stats("2026-09-28", tolerant_rules())

        self.assertIsNone(analyze_symbol(SYMBOL, frame, tolerant_rules(), "2026-09-28", stats))
        self.assertEqual(stats["skipped"]["stale"], 1)

    def test_short_history_counts_as_insufficient(self):
        frame = build_frame(raw_bars(count=30))
        stats = new_stats("2026-09-28", tolerant_rules())

        self.assertIsNone(analyze_symbol(SYMBOL, frame, tolerant_rules(), "2026-09-28", stats))
        self.assertEqual(stats["skipped"]["insufficient"], 1)

    def test_window_with_a_gap_is_not_judged(self):
        """本地少同步了一根，箱体会把断档前后压成一段连续走势，这一组规则不判定。"""
        bars = raw_bars()
        frame = build_frame(pd.concat([bars.iloc[:60], bars.iloc[61:]], ignore_index=True))
        rules = tolerant_rules()
        stats = new_stats("2026-09-28", rules)

        self.assertIsNone(analyze_symbol(SYMBOL, frame, rules, "2026-09-28", stats))
        self.assertEqual(stats["rules"]["1"]["gap"], 1)
        self.assertEqual(stats["skipped"]["gap"], 1)
        self.assertEqual(stats["skipped"]["insufficient"], 0)

    def test_trending_series_is_rejected(self):
        bars = raw_bars()
        bars["close"] = np.linspace(100.0, 160.0, len(bars))
        bars["open"] = bars["close"]
        bars["high"] = bars["close"] * 1.002
        bars["low"] = bars["close"] * 0.998
        rules = tolerant_rules()
        stats = new_stats("2026-09-28", rules)

        self.assertIsNone(analyze_symbol(SYMBOL, build_frame(bars), rules, "2026-09-28", stats))
        self.assertEqual(stats["rules"]["1"]["passed_full"], 0)


class CryptoHengpanScanTest(unittest.TestCase):
    """整条扫描流程走内存库，只验证编排：进度、边扫边出、取消。"""

    def setUp(self):
        self.conn = db.connect(":memory:")
        table = db.kline_table("1h", "perpetual")
        bars = raw_bars()
        rows = [(row.symbol, row.open_time, str(row.open), str(row.high), str(row.low),
                 str(row.close), str(row.volume), row.open_time + INTERVAL_MS - 1,
                 str(row.quote_asset_volume), int(row.number_of_trades), "0", "0", "0")
                for row in bars.itertuples(index=False)]
        # 列顺序显式写出，和建表语句一致
        self.conn.executemany(
            f'INSERT OR REPLACE INTO {table} ("symbol","open_time","open","high","low","close",'
            '"volume","close_time","quote_asset_volume","number_of_trades",'
            '"taker_buy_base_asset_volume","taker_buy_quote_asset_volume","ignore") '
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_scan_streams_results_and_reports_progress(self):
        rules = tolerant_rules()
        stats = new_stats("2026-09-28", rules)
        streamed = []
        progress = []

        found = scan_hengpan(self.conn, [SYMBOL], rules, "2026-09-28", stats,
                             update_progress=lambda **kw: progress.append(kw),
                             on_found=streamed.append)

        self.assertEqual([item["symbol"] for item in found], ["BTCUSDT"])
        self.assertEqual([item["symbol"] for item in streamed], ["BTCUSDT"])
        self.assertEqual(progress[-1]["scanned"], 1)
        self.assertIn("扫描完成", progress[-1]["message"])

    def test_cancelled_scan_returns_nothing_and_says_so(self):
        rules = tolerant_rules()
        stats = new_stats("2026-09-28", rules)
        progress = []

        found = scan_hengpan(self.conn, [SYMBOL], rules, "2026-09-28", stats,
                             update_progress=lambda **kw: progress.append(kw),
                             should_cancel=lambda: True)

        self.assertEqual(found, [])
        self.assertIn("已停止", progress[-1]["message"])

    def test_missing_symbol_counts_as_stale(self):
        rules = tolerant_rules()
        stats = new_stats("2026-09-28", rules)

        found = scan_hengpan(self.conn, [{**SYMBOL, "symbol": "NOPEUSDT"}], rules,
                             "2026-09-28", stats)

        self.assertEqual(found, [])
        self.assertEqual(stats["skipped"]["stale"], 1)


if __name__ == "__main__":
    unittest.main()
