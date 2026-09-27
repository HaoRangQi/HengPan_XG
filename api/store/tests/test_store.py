"""建表、增量规则、清理的回归测试。不联网，Baostock 调用全部替换成假数据。"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd

from api.store import db, sync
from api.store.reader import load_kline_60m


def fake_rs(frame):
    """伪造 Baostock 的结果集：error_code / fields / next() / get_row_data()。"""
    class _RS:
        error_code = "0"
        error_msg = ""
        fields = list(frame.columns)

        def __init__(self):
            self._rows = frame.astype(str).values.tolist()
            self._i = -1

        def next(self):
            self._i += 1
            return self._i < len(self._rows)

        def get_row_data(self):
            return self._rows[self._i]
    return _RS()


def kline_frame(code, days, slots=("103000000", "113000000", "140000000", "150000000")):
    rows = []
    for day in days:
        for slot in slots:
            rows.append({"date": day, "time": day.replace("-", "") + slot, "code": code,
                         "open": "9.01", "high": "9.05", "low": "8.97", "close": "9.00",
                         "volume": "1000", "amount": "9000", "adjustflag": "3"})
    return pd.DataFrame(rows)


class StoreTestCase(unittest.TestCase):
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


class SchemaTest(StoreTestCase):
    def test_kline_columns_match_baostock_fields(self):
        """K 线表的列名和列数必须与文档的分钟线字段逐一对应，不允许合并或裁剪。"""
        expected = ["date", "time", "code", "open", "high", "low", "close",
                    "volume", "amount", "adjustflag"]
        self.assertEqual(list(db.MINUTE_COLUMNS), expected)
        for board in db.KLINE_BOARDS:
            with self.subTest(board=board):
                info = self.conn.execute(
                    f"PRAGMA table_info({db.kline_table('60', board)})").fetchall()
                self.assertEqual([row["name"] for row in info], expected)

    def test_metadata_tables_keep_interface_field_names(self):
        cases = {
            "stock_basic": ["code", "code_name", "ipoDate", "outDate", "type", "status",
                            "board", "updated_at"],
            "stock_industry": ["code", "code_name", "industry",
                               "industryClassification", "updateDate"],
            "adjust_factor": ["code", "dividOperateDate", "foreAdjustFactor",
                              "backAdjustFactor", "adjustFactor"],
            "trade_calendar": ["calendar_date", "is_trading_day"],
        }
        for table, expected in cases.items():
            with self.subTest(table=table):
                info = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
                self.assertEqual([row["name"] for row in info], expected)

    def test_primary_key_is_code_and_time(self):
        info = self.conn.execute("PRAGMA table_info(kline_60m_sz_gem)").fetchall()
        keyed = sorted((row["pk"], row["name"]) for row in info if row["pk"])
        self.assertEqual(keyed, [(1, "code"), (2, "time")])

    def test_no_extra_indexes(self):
        """第一版只靠主键，不建额外索引（实测加索引反而拖慢批量取数和清理）。"""
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall()
        self.assertEqual([row["name"] for row in rows], [])

    def test_init_schema_is_idempotent(self):
        db.init_schema(self.conn)
        db.init_schema(self.conn)
        self.assertEqual(self.conn.execute(
                         "SELECT COUNT(*) FROM kline_60m_sz_gem").fetchone()[0], 0)

    def test_store_meta_round_trip(self):
        self.assertIsNone(db.get_meta(self.conn, "missing"))
        db.set_meta(self.conn, "factor:sz_gem", "complete")
        self.assertEqual(db.get_meta(self.conn, "factor:sz_gem"), "complete")

    def test_union_view_exposes_all_boards(self):
        for board in ("sh_main", "sz_gem"):
            db.upsert(self.conn, db.kline_table("60", board), db.MINUTE_COLUMNS,
                      [("2026-09-24", "20260924150000000", f"{board}.1",
                        "1", "2", "0.5", "1.5", "10", "20", "3")])
        rows = self.conn.execute(
            "SELECT board, code FROM kline_60m_all ORDER BY board").fetchall()
        self.assertEqual([r["board"] for r in rows], ["sh_main", "sz_gem"])

    def test_board_of_covers_known_prefixes(self):
        cases = {"sh.600000": "sh_main", "sh.605001": "sh_main", "sh.688981": "sh_star",
                 "sz.000001": "sz_main", "sz.003000": "sz_main", "sz.300750": "sz_gem",
                 "sz.301001": "sz_gem", "sz.302132": "sz_gem", "bj.830799": "bj"}
        for code, board in cases.items():
            with self.subTest(code=code):
                self.assertEqual(db.board_of(code), board)
        self.assertIsNone(db.board_of("sh.900001"))


class UpsertTest(StoreTestCase):
    def test_same_bar_is_overwritten_not_duplicated(self):
        table = db.kline_table("60", "sz_gem")
        row = ["2026-09-24", "20260924150000000", "sz.300750",
               "1", "2", "0.5", "1.5", "10", "20", "3"]
        db.upsert(self.conn, table, db.MINUTE_COLUMNS, [tuple(row)])
        row[6] = "9.99"          # close 改了，重复同步应覆盖
        db.upsert(self.conn, table, db.MINUTE_COLUMNS, [tuple(row)])
        self.conn.commit()
        rows = self.conn.execute(f"SELECT close FROM {table}").fetchall()
        self.assertEqual([r["close"] for r in rows], ["9.99"])

    def test_latest_time_reads_last_bar(self):
        table = db.kline_table("60", "sz_gem")
        db.upsert(self.conn, table, db.MINUTE_COLUMNS,
                  [tuple(kline_frame("sz.300750", ["2026-09-23", "2026-09-24"]).iloc[i])
                   for i in range(8)])
        self.conn.commit()
        self.assertEqual(db.latest_time(self.conn, "60", "sz_gem", "sz.300750"),
                         "20260924150000000")
        self.assertIsNone(db.latest_time(self.conn, "60", "sz_gem", "sz.300751"))

    def test_stock_list_with_kline_excludes_unsynced_stocks(self):
        now = datetime.now().isoformat(timespec="seconds")
        db.upsert(self.conn, "stock_basic",
                  ("code", "code_name", "ipoDate", "outDate", "type", "status", "board", "updated_at"), [
                      ("sz.300750", "有行情", "", "", "1", "1", "sz_gem", now),
                      ("sz.300751", "无行情", "", "", "1", "1", "sz_gem", now),
                  ])
        db.upsert(self.conn, db.kline_table("60", "sz_gem"), db.MINUTE_COLUMNS, [
            ("2026-09-24", "20260924150000000", "sz.300750", "1", "2", "0.5", "1.5", "10", "20", "3")
        ])
        self.conn.commit()
        self.assertEqual([s["code"] for s in db.stock_list_with_kline(self.conn, boards=["sz_gem"])],
                         ["sz.300750"])

    def test_reader_normalises_and_applies_qfq(self):
        table = db.kline_table("60", "sz_gem")
        db.upsert(self.conn, table, db.MINUTE_COLUMNS, [
            ("2026-09-23", "20260923103000000", "sz.300750", "10", "12", "8", "10", "100", "1000", "3"),
            ("2026-09-24", "20260924103000000", "sz.300750", "5", "6", "4", "5", "100", "500", "3"),
        ])
        db.upsert(self.conn, "adjust_factor", sync.ADJUST_COLUMNS, [
            ("sz.300750", "2026-09-23", "1", "2", "2"),
            ("sz.300750", "2026-09-24", "1", "4", "2"),
        ])
        self.conn.commit()
        frame = load_kline_60m(self.conn, ["sz_gem"], adjust="qfq", codes=["sz.300750"])
        self.assertEqual(frame["date"].tolist(), ["2026-09-23 10:30:00", "2026-09-24 10:30:00"])
        self.assertEqual(frame["close"].tolist(), [5.0, 5.0])
        self.assertEqual(frame["tradestatus"].tolist(), ["1", "1"])


class IncrementalPlanTest(StoreTestCase):
    def test_start_date_falls_back_to_retention_window(self):
        end = "2026-09-24"
        plan = sync.plan_start_dates(self.conn, "60", "sz_gem", ["sz.300750"], end)
        expected = (datetime.strptime(end, "%Y-%m-%d")
                    - timedelta(days=sync.RETENTION_DAYS)).strftime("%Y-%m-%d")
        self.assertEqual(plan["sz.300750"], expected)

    def test_start_date_resumes_from_last_local_bar(self):
        """有本地数据时从最后一根那天重新拉：当天可能只存了上午的，重拉覆盖。"""
        table = db.kline_table("60", "sz_gem")
        frame = kline_frame("sz.300750", ["2026-09-23"], slots=("103000000", "113000000"))
        db.upsert(self.conn, table, db.MINUTE_COLUMNS,
                  [tuple(frame.iloc[i]) for i in range(len(frame))])
        self.conn.commit()
        plan = sync.plan_start_dates(self.conn, "60", "sz_gem", ["sz.300750"], "2026-09-24")
        self.assertEqual(plan["sz.300750"], "2026-09-23")

    def test_start_date_never_predates_retention_window(self):
        table = db.kline_table("60", "sz_gem")
        frame = kline_frame("sz.300750", ["2020-01-02"])
        db.upsert(self.conn, table, db.MINUTE_COLUMNS,
                  [tuple(frame.iloc[i]) for i in range(len(frame))])
        self.conn.commit()
        end = "2026-09-24"
        plan = sync.plan_start_dates(self.conn, "60", "sz_gem", ["sz.300750"], end)
        floor = (datetime.strptime(end, "%Y-%m-%d")
                 - timedelta(days=sync.RETENTION_DAYS)).strftime("%Y-%m-%d")
        self.assertEqual(plan["sz.300750"], floor)

    def test_date_of_parses_baostock_time(self):
        self.assertEqual(sync._date_of("20260924150000000"), "2026-09-24")


class MetadataSyncTest(StoreTestCase):
    @patch("baostock.query_trade_dates")
    def test_trade_calendar_round_trip(self, query):
        query.return_value = fake_rs(pd.DataFrame([
            {"calendar_date": "2026-09-24", "is_trading_day": "1"},
            {"calendar_date": "2026-09-25", "is_trading_day": "0"},
            {"calendar_date": "2026-09-26", "is_trading_day": "1"},
        ]))
        with patch("api.data_fetcher.baostock_login"):
            sync.sync_trade_calendar(self.conn)
        self.assertEqual(db.trading_days(self.conn), ["2026-09-24", "2026-09-26"])
        self.assertEqual(sync.resolve_end_date(self.conn), "2026-09-26")

    @patch("baostock.query_stock_basic")
    def test_stock_basic_keeps_only_listed_stocks_and_tags_board(self, query):
        query.return_value = fake_rs(pd.DataFrame([
            {"code": "sz.300750", "code_name": "宁德时代", "ipoDate": "2018-06-11",
             "outDate": "", "type": "1", "status": "1"},
            {"code": "sh.000001", "code_name": "上证指数", "ipoDate": "1991-07-15",
             "outDate": "", "type": "2", "status": "1"},      # 指数，应排除
            {"code": "bj.830799", "code_name": "艾能聚", "ipoDate": "2021-01-01",
             "outDate": "", "type": "1", "status": "1"},      # 北交所，Baostock 不支持
        ]))
        with patch("api.data_fetcher.baostock_login"):
            written = sync.sync_stock_basic(self.conn)
        self.assertEqual(written, 1)
        row = self.conn.execute("SELECT code, board FROM stock_basic").fetchone()
        self.assertEqual((row["code"], row["board"]), ("sz.300750", "sz_gem"))

    @patch("baostock.query_stock_industry")
    @patch("baostock.query_stock_basic")
    def test_stock_list_joins_industry(self, basic, industry):
        basic.return_value = fake_rs(pd.DataFrame([
            {"code": "sz.300750", "code_name": "宁德时代", "ipoDate": "2018-06-11",
             "outDate": "", "type": "1", "status": "1"},
            {"code": "sz.300751", "code_name": "迈为股份", "ipoDate": "2018-11-09",
             "outDate": "", "type": "1", "status": "0"},      # 已退市
        ]))
        industry.return_value = fake_rs(pd.DataFrame([
            {"updateDate": "2026-09-21", "code": "sz.300750", "code_name": "宁德时代",
             "industry": "电气设备", "industryClassification": "证监会行业分类"},
        ]))
        with patch("api.data_fetcher.baostock_login"):
            sync.sync_stock_basic(self.conn)
            sync.sync_stock_industry(self.conn)
        listed = db.stock_list(self.conn, ["sz_gem"])
        self.assertEqual([s["code"] for s in listed], ["sz.300750"])
        self.assertEqual(listed[0]["industry"], "电气设备")
        # 没有行业记录时给默认值，不能是 None
        with_delisted = db.stock_list(self.conn, ["sz_gem"], include_delisted=True)
        self.assertEqual(len(with_delisted), 2)
        self.assertEqual(with_delisted[1]["industry"], "未知行业")

    @patch("baostock.query_daily_adjust_factor")
    def test_adjust_factor_tolerates_days_without_dividends(self, query):
        """当天没有除权就是空结果，属于正常，不能当失败重试。"""
        frames = {
            "2026-09-24": pd.DataFrame([{"code": "sh.600000", "dividOperateDate": "2026-09-24",
                                         "foreAdjustFactor": "1.0",
                                         "backAdjustFactor": "13.367013",
                                         "adjustFactor": "13.367013"}]),
            "2026-09-23": pd.DataFrame(columns=list(sync.ADJUST_COLUMNS)),
        }
        query.side_effect = lambda date: fake_rs(frames[date])
        with patch("api.data_fetcher.baostock_login"):
            written, requests = sync.sync_adjust_factor_by_day(
                self.conn, ["2026-09-23", "2026-09-24"])
        self.assertEqual((written, requests), (1, 2))
        row = self.conn.execute("SELECT backAdjustFactor FROM adjust_factor").fetchone()
        self.assertEqual(row["backAdjustFactor"], "13.367013")


class CleanupTest(StoreTestCase):
    def _seed(self, days):
        table = db.kline_table("60", "sz_gem")
        frame = kline_frame("sz.300750", days)
        db.upsert(self.conn, table, db.MINUTE_COLUMNS,
                  [tuple(frame.iloc[i]) for i in range(len(frame))])
        self.conn.commit()

    def test_dry_run_reports_without_deleting(self):
        old = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
        new = datetime.now().strftime("%Y-%m-%d")
        self._seed([old, new])
        preview = sync.cleanup(self.conn, keep_days=60, boards=["sz_gem"], dry_run=True)
        self.assertEqual(preview["total"], 4)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM kline_60m_sz_gem").fetchone()[0], 8)

    def test_apply_deletes_and_logs(self):
        old = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
        new = datetime.now().strftime("%Y-%m-%d")
        self._seed([old, new])
        result = sync.cleanup(self.conn, keep_days=60, boards=["sz_gem"], dry_run=False)
        self.assertEqual(result["total"], 4)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM kline_60m_sz_gem").fetchone()[0], 4)
        self.assertEqual(sync.recent_logs(self.conn, 1)[0]["action"], "cleanup")


class SyncLogTest(StoreTestCase):
    def test_log_records_request_count(self):
        log_id = sync.start_log(self.conn, "sync", ["sz_gem"])
        sync.finish_log(self.conn, log_id, "completed",
                        {"requests": 1408, "rows": 5000, "failed": 2})
        log = sync.recent_logs(self.conn, 1)[0]
        self.assertEqual((log["status"], log["requests"], log["rows"], log["failed"]),
                         ("completed", 1408, 5000, 2))


class ExplicitRangeTest(StoreTestCase):
    """补历史区间：指定 start_date 后，所有股票都从该日拉，不再看本地进度。"""

    def _seed(self, code, days):
        table = db.kline_table("60", db.board_of(code))
        frame = kline_frame(code, days)
        db.upsert(self.conn, table, db.MINUTE_COLUMNS,
                  [tuple(frame.iloc[i]) for i in range(len(frame))])
        self.conn.commit()

    def test_explicit_start_overrides_local_progress(self):
        self._seed("sz.300750", ["2026-09-23"])
        plan = sync.plan_start_dates(self.conn, "60", "sz_gem", ["sz.300750", "sz.300751"],
                                     "2026-09-24", start_date="2026-03-01")
        self.assertEqual(plan, {"sz.300750": "2026-03-01", "sz.300751": "2026-03-01"})

    def test_explicit_start_may_predate_retention_window(self):
        """补 3 月的历史时不能被 60 天保留期截断，否则补历史就没意义了。"""
        plan = sync.plan_start_dates(self.conn, "60", "sz_gem", ["sz.300750"],
                                     "2026-09-24", start_date="2026-01-05")
        self.assertEqual(plan["sz.300750"], "2026-01-05")

    def test_without_explicit_start_still_incremental(self):
        self._seed("sz.300750", ["2026-09-23"])
        plan = sync.plan_start_dates(self.conn, "60", "sz_gem", ["sz.300750"], "2026-09-24")
        self.assertEqual(plan["sz.300750"], "2026-09-23")

    def test_sync_all_forwards_range_and_codes_to_kline(self):
        """区间和股票范围要从 sync_all 一路传到 sync_kline，不能中途丢掉。"""
        captured = {}

        def fake_sync_kline(conn, **kwargs):
            captured.update(kwargs)
            return {"rows": 0, "requests": 0, "failed": 0, "cancelled": False,
                    "start_date": kwargs.get("start_date"), "end_date": kwargs.get("end_date"),
                    "up_to_date": 0, "probe": 0}

        db.upsert(self.conn, "trade_calendar", ("calendar_date", "is_trading_day"),
                  [("2026-05-29", "1"), ("2026-05-30", "0"), ("2026-05-31", "0"),
                   ("2026-09-24", "1")])
        db.set_meta(self.conn, "adjust_factor_daily_through", "2026-09-24")
        self.conn.commit()
        with patch("api.store.sync.sync_trade_calendar", return_value=0), \
             patch("api.store.sync._metadata_is_stale", return_value=False), \
             patch("api.store.sync.sync_kline", side_effect=fake_sync_kline), \
             patch("api.store.sync.sync_adjust_factor_by_day", return_value=(0, 0)):
            sync.sync_all(self.conn, boards=["sz_gem"], start="2026-03-01",
                          end="2026-05-31", codes=["sz.300750"])
        self.assertEqual(captured["start_date"], "2026-03-01")
        # 05-31 是星期天，截止日退到之前最近的交易日 05-29
        self.assertEqual(captured["end_date"], "2026-05-29")
        self.assertEqual(captured["codes"], ["sz.300750"])

    def test_sync_kline_rejects_reversed_range(self):
        with self.assertRaises(ValueError):
            sync.sync_kline(self.conn, boards=["sz_gem"],
                            start_date="2026-09-30", end_date="2026-03-01")


class StockInventoryTest(StoreTestCase):
    def setUp(self):
        super().setUp()
        now = datetime.now().isoformat(timespec="seconds")
        db.upsert(self.conn, "stock_basic",
                  ("code", "code_name", "ipoDate", "outDate", "type", "status",
                   "board", "updated_at"), [
                      ("sz.300750", "宁德时代", "2018-06-11", "", "1", "1", "sz_gem", now),
                      ("sz.300751", "迈为股份", "2018-11-09", "", "1", "1", "sz_gem", now),
                      ("sz.300752", "已退市", "2019-01-01", "2026-01-01", "1", "0", "sz_gem", now),
                      ("sh.600000", "浦发银行", "1999-11-10", "", "1", "1", "sh_main", now),
                  ])
        db.upsert(self.conn, "stock_industry",
                  ("code", "code_name", "industry", "industryClassification", "updateDate"),
                  [("sz.300750", "宁德时代", "电气设备", "证监会行业分类", "2026-09-21")])
        frame = kline_frame("sz.300750", ["2026-09-23", "2026-09-24"])
        db.upsert(self.conn, db.kline_table("60", "sz_gem"), db.MINUTE_COLUMNS,
                  [tuple(frame.iloc[i]) for i in range(len(frame))])
        self.conn.commit()

    def test_reports_bar_count_and_date_range(self):
        rows = {s["code"]: s for s in db.stock_inventory(self.conn, ["sz_gem"])}
        self.assertEqual(rows["sz.300750"]["bars"], 8)
        self.assertEqual(rows["sz.300750"]["first_date"], "2026-09-23")
        self.assertEqual(rows["sz.300750"]["last_date"], "2026-09-24")
        self.assertEqual(rows["sz.300750"]["industry"], "电气设备")
        # 没有行情的股票也要列出来，bars 为 0 而不是缺行
        self.assertEqual(rows["sz.300751"]["bars"], 0)
        self.assertIsNone(rows["sz.300751"]["first_date"])
        self.assertEqual(rows["sz.300751"]["industry"], "未知行业")

    def test_delisted_hidden_by_default(self):
        codes = [s["code"] for s in db.stock_inventory(self.conn, ["sz_gem"])]
        self.assertNotIn("sz.300752", codes)
        codes = [s["code"] for s in db.stock_inventory(self.conn, ["sz_gem"],
                                                        include_delisted=True)]
        self.assertIn("sz.300752", codes)

    def test_having_filter(self):
        self.assertEqual([s["code"] for s in db.stock_inventory(
            self.conn, ["sz_gem"], having="with")], ["sz.300750"])
        self.assertEqual([s["code"] for s in db.stock_inventory(
            self.conn, ["sz_gem"], having="without")], ["sz.300751"])

    def test_keyword_matches_code_or_name(self):
        self.assertEqual([s["code"] for s in db.stock_inventory(
            self.conn, ["sz_gem"], keyword="300750")], ["sz.300750"])
        self.assertEqual([s["code"] for s in db.stock_inventory(
            self.conn, ["sz_gem"], keyword="迈为")], ["sz.300751"])

    def test_multiple_boards_are_merged(self):
        codes = [s["code"] for s in db.stock_inventory(self.conn, ["sz_gem", "sh_main"])]
        self.assertEqual(codes, ["sz.300750", "sz.300751", "sh.600000"])

    def test_unknown_board_rejected(self):
        with self.assertRaises(ValueError):
            db.stock_inventory(self.conn, ["bj"])

    def test_kline_range_counts_within_window(self):
        self.assertEqual(db.kline_range(self.conn, "sz.300750")["bars"], 8)
        self.assertEqual(db.kline_range(self.conn, "sz.300750",
                                        start="2026-09-24")["bars"], 4)
        self.assertEqual(db.kline_range(self.conn, "bj.830799")["bars"], 0)


class SkipUpToDateTest(StoreTestCase):
    """已是最新的股票不发请求：重复点同步应该是 0 次请求。"""

    def setUp(self):
        super().setUp()
        now = datetime.now().isoformat(timespec="seconds")
        db.upsert(self.conn, "stock_basic",
                  ("code", "code_name", "ipoDate", "outDate", "type", "status",
                   "board", "updated_at"),
                  [(f"sz.30{i:04d}", f"股票{i}", "", "", "1", "1", "sz_gem", now)
                   for i in range(3)])
        self.conn.commit()

    def _seed(self, code, day, slots=("103000000", "113000000", "140000000", "150000000")):
        frame = kline_frame(code, [day], slots=slots)
        db.upsert(self.conn, db.kline_table("60", "sz_gem"), db.MINUTE_COLUMNS,
                  [tuple(frame.iloc[i]) for i in range(len(frame))])
        self.conn.commit()

    def test_complete_stock_is_left_out_of_the_plan(self):
        self._seed("sz.300000", "2026-09-24")                                   # 有 15:00，已最新
        self._seed("sz.300001", "2026-09-24", slots=("103000000", "113000000"))  # 只有上午
        self._seed("sz.300002", "2026-09-23")                                   # 缺一天
        plan = sync.plan_start_dates(self.conn, "60", "sz_gem",
                                     ["sz.300000", "sz.300001", "sz.300002"], "2026-09-24")
        self.assertEqual(plan, {"sz.300001": "2026-09-24", "sz.300002": "2026-09-23"})

    def test_explicit_range_still_refetches_complete_stocks(self):
        """补历史区间是主动要求覆盖，不能因为「已是最新」就跳过。"""
        self._seed("sz.300000", "2026-09-24")
        plan = sync.plan_start_dates(self.conn, "60", "sz_gem", ["sz.300000"],
                                     "2026-09-24", start_date="2026-09-01")
        self.assertEqual(plan, {"sz.300000": "2026-09-01"})

    def test_all_up_to_date_makes_no_request_and_opens_no_pool(self):
        for code in ("sz.300000", "sz.300001", "sz.300002"):
            self._seed(code, "2026-09-24")
        with patch("api.store.sync.ProcessPoolExecutor",
                   side_effect=AssertionError("不该开进程池")), \
             patch("api.store.sync.fetch_kline_rows",
                   side_effect=AssertionError("不该发请求")):
            stats = sync.sync_kline(self.conn, boards=["sz_gem"], end_date="2026-09-24")
        self.assertEqual((stats["requests"], stats["up_to_date"], stats["rows"]), (0, 3, 0))


class ProbeTest(StoreTestCase):
    """批量同步前先探测数据源，没更新就只花几次请求。"""

    END = "2026-09-28"

    def rows_for(self, code, days):
        frame = kline_frame(code, days)
        return [tuple(frame.iloc[i]) for i in range(len(frame))]

    def tasks(self, codes):
        return [("sz_gem", code, "2026-09-24") for code in codes]

    def test_probe_passes_on_first_stock_with_end_date(self):
        """第一只探测股停牌、拿不到截止日；第二只拿到了，就放行其余任务。探测拿到的数据照常写库。"""
        codes = ["sz.300000", "sz.300001", "sz.300002", "sz.300003"]
        responses = {"sz.300000": self.rows_for("sz.300000", ["2026-09-24"]),
                     "sz.300001": self.rows_for("sz.300001", ["2026-09-24", self.END])}
        stats = {"requests": 0, "probe": 0, "rows": 0, "failed": 0}
        with patch("api.store.sync.fetch_kline_rows",
                   side_effect=lambda code, *args, **kwargs: responses[code]):
            remaining = sync._probe_source(self.conn, self.tasks(codes), "60", self.END, stats)
        self.assertEqual([task[1] for task in remaining], ["sz.300002", "sz.300003"])
        self.assertEqual((stats["requests"], stats["probe"], stats["rows"]), (2, 2, 12))
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM kline_60m_sz_gem").fetchone()[0], 12)

    def test_probe_stops_when_source_not_updated(self):
        codes = [f"sz.30{i:04d}" for i in range(100)]
        stats = {"requests": 0, "probe": 0, "rows": 0, "failed": 0}
        with patch("api.store.sync.fetch_kline_rows",
                   side_effect=lambda code, *args, **kwargs: self.rows_for(code, ["2026-09-24"])):
            with self.assertRaisesRegex(ConnectionError, "尚未入库"):
                sync._probe_source(self.conn, self.tasks(codes), "60", self.END, stats)
        # 100 只待同步，只花了 PROBE_LIMIT 次请求
        self.assertEqual(stats["requests"], sync.PROBE_LIMIT)

    def test_probe_prefers_large_caps(self):
        tasks = [("sz_main", "sz.000009", "2026-09-24"), ("sh_main", "sh.600000", "2026-09-24")]
        called = []

        def fake(code, *args, **kwargs):
            called.append(code)
            return self.rows_for(code, [self.END])

        stats = {"requests": 0, "probe": 0, "rows": 0, "failed": 0}
        with patch("api.store.sync.fetch_kline_rows", side_effect=fake):
            sync._probe_source(self.conn, tasks, "60", self.END, stats)
        self.assertEqual(called, ["sh.600000"])

    def test_probe_propagates_blacklist(self):
        from api.data_fetcher import BaostockBlacklisted
        stats = {"requests": 0, "probe": 0, "rows": 0, "failed": 0}
        with patch("api.store.sync.fetch_kline_rows",
                   side_effect=BaostockBlacklisted("黑名单用户")):
            with self.assertRaisesRegex(ConnectionError, "黑名单"):
                sync._probe_source(self.conn, self.tasks(["sz.300000"]), "60", self.END, stats)
        self.assertEqual(stats["requests"], 1)   # 黑名单立刻停，不再试下一只


class EndDateAndCalendarTest(StoreTestCase):
    def setUp(self):
        super().setUp()
        db.upsert(self.conn, "trade_calendar", ("calendar_date", "is_trading_day"),
                  [("2026-09-24", "1"), ("2026-09-25", "0"), ("2026-09-26", "0"),
                   ("2026-09-27", "0"), ("2026-09-28", "1")])
        self.conn.commit()

    def test_end_date_snaps_back_to_trading_day(self):
        with patch("api.store.sync._today", return_value="2026-09-28"):
            self.assertEqual(sync.resolve_end_date(self.conn, "2026-09-27"), "2026-09-24")
            self.assertEqual(sync.resolve_end_date(self.conn), "2026-09-28")
            # 未来日期按今天算
            self.assertEqual(sync.resolve_end_date(self.conn, "2026-12-31"), "2026-09-28")

    def test_calendar_refetched_only_when_it_ends_before_today(self):
        with patch("api.store.sync._today", return_value="2026-09-28"):
            self.assertFalse(sync._calendar_is_stale(self.conn))
        with patch("api.store.sync._today", return_value="2026-09-29"):
            self.assertTrue(sync._calendar_is_stale(self.conn))
        self.conn.execute("DELETE FROM trade_calendar")
        self.assertTrue(sync._calendar_is_stale(self.conn))


if __name__ == "__main__":
    unittest.main()
