"""本地 K 线读取、类型转换和复权的回归测试。"""
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from api.store import db
from api.store.reader import _format_times, _normalise_minute_time, load_kline_60m


class ReaderTestCase(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(self.path)
        self.conn = db.connect(self.path)

    def tearDown(self):
        self.conn.close()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(self.path + suffix):
                os.unlink(self.path + suffix)

    def seed_bar(self, board, date, time, code, prices, volume="1000",
                 amount="9000", adjustflag="3"):
        row = (date, time, code, *prices, volume, amount, adjustflag)
        db.upsert(self.conn, db.kline_table("60", board), db.MINUTE_COLUMNS, [row])

    def seed_factor(self, code, date, back):
        db.upsert(
            self.conn,
            "adjust_factor",
            ("code", "dividOperateDate", "foreAdjustFactor",
             "backAdjustFactor", "adjustFactor"),
            [(code, date, "ignored", str(back), "ignored")],
        )


class LoadKline60mTest(ReaderTestCase):
    def test_reads_requested_boards_dates_and_codes_with_scanner_columns(self):
        self.seed_bar("sh_main", "2026-09-23", "20260923150000000", "sh.600000",
                      ("9.0", "9.2", "8.9", "9.1"))
        self.seed_bar("sh_main", "2026-09-24", "20260924103000000", "sh.600000",
                      ("9.1", "9.3", "9.0", "9.2"), volume="", amount="bad")
        self.seed_bar("sz_gem", "2026-09-24", "20260924103000000", "sz.300750",
                      ("200", "202", "198", "201"))
        self.seed_bar("sh_star", "2026-09-24", "20260924103000000", "sh.688001",
                      ("50", "51", "49", "50.5"))
        self.conn.commit()

        frame = load_kline_60m(
            self.conn,
            ["sh_main", "sz_gem"],
            "2026-09-24",
            "2026-09-24",
            adjust="raw",
            codes=["sh.600000", "sz.300750"],
        )

        self.assertEqual(frame["code"].tolist(), ["sh.600000", "sz.300750"])
        self.assertEqual(frame["date"].tolist(), ["2026-09-24 10:30:00", "2026-09-24 10:30:00"])
        self.assertEqual(frame["time"].tolist(),
                         ["2026-09-24 10:30:00", "2026-09-24 10:30:00"])
        self.assertEqual(frame.loc[0, "close"], 9.2)
        self.assertTrue(np.isnan(frame.loc[0, "volume"]))
        self.assertTrue(np.isnan(frame.loc[0, "amount"]))
        self.assertTrue(frame["turn"].isna().all())
        self.assertEqual(frame["tradestatus"].tolist(), ["1", "1"])
        self.assertEqual(frame["isST"].tolist(), ["0", "0"])

    def test_applies_factor_effective_on_each_bar_and_latest_factor_for_qfq(self):
        code = "sh.600000"
        self.seed_bar("sh_main", "2026-07-10", "20260710150000000", code,
                      ("10", "12", "8", "11"))
        self.seed_bar("sh_main", "2026-07-16", "20260716150000000", code,
                      ("10", "12", "8", "11"))
        self.seed_factor(code, "2020-01-01", 2)
        self.seed_factor(code, "2026-07-16", 4)
        # 即便查询截止在 7 月，前复权分母也必须用库内最新累计因子。
        self.seed_factor(code, "2026-09-24", 5)
        self.conn.commit()

        frame = load_kline_60m(
            self.conn, ["sh_main"], "2026-07-01", "2026-07-31", adjust="qfq")

        np.testing.assert_allclose(frame["open"], [4.0, 8.0])
        np.testing.assert_allclose(frame["high"], [4.8, 9.6])
        np.testing.assert_allclose(frame["low"], [3.2, 6.4])
        np.testing.assert_allclose(frame["close"], [4.4, 8.8])

    def test_supports_hfq_raw_and_stocks_without_factor_history(self):
        adjusted = "sh.600000"
        unchanged = "sh.600001"
        self.seed_bar("sh_main", "2026-07-10", "20260710150000000", adjusted,
                      ("10", "12", "8", "11"))
        self.seed_bar("sh_main", "2026-07-10", "20260710150000000", unchanged,
                      ("20", "22", "18", "21"))
        self.seed_factor(adjusted, "2020-01-01", 2)
        self.conn.commit()

        hfq = load_kline_60m(
            self.conn, ["sh_main"], "2026-07-10", "2026-07-10", adjust="hfq")
        raw = load_kline_60m(
            self.conn, ["sh_main"], "2026-07-10", "2026-07-10", adjust="raw")

        np.testing.assert_allclose(hfq["open"], [20.0, 20.0])
        np.testing.assert_allclose(raw["open"], [10.0, 20.0])
        self.assertEqual(hfq["volume"].tolist(), raw["volume"].tolist())
        self.assertEqual(hfq["amount"].tolist(), raw["amount"].tolist())

    def test_empty_code_filter_returns_empty_frame_with_stable_columns(self):
        self.seed_bar("sh_main", "2026-09-24", "20260924103000000", "sh.600000",
                      ("9", "10", "8", "9.5"))
        self.conn.commit()
        frame = load_kline_60m(
            self.conn, ["sh_main"], "2026-09-01", "2026-09-30", codes=[])
        self.assertTrue(frame.empty)
        self.assertEqual(
            frame.columns.tolist(),
            ["date", "time", "code", "open", "high", "low", "close", "volume",
             "amount", "adjustflag", "turn", "tradestatus", "isST"],
        )

    def test_rejects_unknown_adjustment_mode(self):
        with self.assertRaisesRegex(ValueError, "adjust"):
            load_kline_60m(
                self.conn, ["sh_main"], "2026-09-01", "2026-09-30", adjust="sideways")


class FormatTimesTest(unittest.TestCase):
    """时间格式化走向量化字符串切片，必须和逐行解析结果完全一致。"""

    def test_matches_row_by_row_parser(self):
        frame = pd.DataFrame([
            {"date": "2026-09-24", "time": f"202609{day:02d}{hour:02d}3000000"}
            for day in (23, 24) for hour in (10, 11, 14, 15)
        ])
        expected = [_normalise_minute_time(day, value)
                    for day, value in zip(frame["date"], frame["time"])]
        self.assertEqual(_format_times(frame).tolist(), expected)

    def test_falls_back_for_malformed_time(self):
        frame = pd.DataFrame([
            {"date": "2026-09-24", "time": "20260924150000000"},   # 正常
            {"date": "2026-09-24", "time": "15:00:00"},            # 只有时分秒
            {"date": "2026-09-24", "time": ""},                    # 空
        ])
        self.assertEqual(_format_times(frame).tolist(), [
            "2026-09-24 15:00:00", "2026-09-24 15:00:00", "2026-09-24 00:00:00"])


if __name__ == "__main__":
    unittest.main()
