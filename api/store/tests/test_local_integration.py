"""本地行情 CRUD 和离线横盘分析集成测试，全程不访问 Baostock。"""
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch

from api.hengpan.router import HengpanRule
from api.hengpan.scanner import new_stats, scan_anchored_box
from api.store import db, sync
from api.store.reader import load_kline_60m
from api.store.router import (RefetchRequest, clear_store_board, delete_store_kline,
                              refetch_store_kline)


class ThreadPoolAsProcessPool:
    """让扫描集成测试保留并发调度，同时可以监控联网入口。"""

    def __init__(self, max_workers=None, initializer=None, **_kwargs):
        self._pool = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn, *args, **kwargs):
        return self._pool.submit(fn, *args, **kwargs)

    def shutdown(self, wait=True, cancel_futures=False):
        self._pool.shutdown(wait=wait, cancel_futures=cancel_futures)


class LocalStoreIntegrationTest(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(self.path)
        self.conn = db.connect(self.path)
        self.db_path_patch = patch.object(db, "DB_PATH", self.path)
        self.db_path_patch.start()

    def tearDown(self):
        self.db_path_patch.stop()
        self.conn.close()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(self.path + suffix):
                os.unlink(self.path + suffix)

    @staticmethod
    def bar(code, day, slot="150000000", close="10.00"):
        return (
            day, day.replace("-", "") + slot, code,
            "10.00", "10.05", "9.95", close, "1000", "10000", "3",
        )

    def test_create_update_read_and_range_delete(self):
        table = db.kline_table("60", "sz_gem")
        first = self.bar("sz.300001", "2026-09-23", close="10.00")
        second = self.bar("sz.300001", "2026-09-24", close="10.10")

        self.assertEqual(db.upsert(self.conn, table, db.MINUTE_COLUMNS, [first, second]), 2)
        self.conn.commit()

        updated = list(second)
        updated[6] = "10.88"
        self.assertEqual(db.upsert(self.conn, table, db.MINUTE_COLUMNS, [tuple(updated)]), 1)
        self.conn.commit()

        frame = load_kline_60m(
            self.conn, ["sz_gem"], start="2026-09-23", end="2026-09-24",
            adjust="raw", codes=["sz.300001"],
        )
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame["close"].tolist(), [10.0, 10.88])

        result = delete_store_kline(
            code="sz.300001", start="2026-09-24", end="2026-09-24")
        self.assertEqual(result["deleted"], 1)
        remaining = self.conn.execute(f"SELECT date, close FROM {table}").fetchall()
        self.assertEqual([(row["date"], row["close"]) for row in remaining],
                         [("2026-09-23", "10.00")])

    def test_cleanup_clear_and_vacuum_maintenance(self):
        table = db.kline_table("60", "sz_gem")
        old_day = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
        new_day = datetime.now().strftime("%Y-%m-%d")
        rows = [self.bar("sz.300001", old_day), self.bar("sz.300001", new_day)]
        db.upsert(self.conn, table, db.MINUTE_COLUMNS, rows)
        self.conn.commit()

        preview = sync.cleanup(
            self.conn, keep_days=60, boards=["sz_gem"], dry_run=True)
        self.assertEqual(preview["total"], 1)
        self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 2)

        applied = sync.cleanup(
            self.conn, keep_days=60, boards=["sz_gem"], dry_run=False)
        self.assertEqual(applied["total"], 1)
        self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 1)

        cleared = clear_store_board("sz_gem")
        self.assertEqual(cleared["deleted"], 1)
        self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

        vacuumed = sync.vacuum(self.conn)
        self.assertGreaterEqual(vacuumed["before"], vacuumed["after"])
        self.assertEqual(vacuumed["freed"], vacuumed["before"] - vacuumed["after"])

    def test_refetch_replaces_range_without_real_network(self):
        table = db.kline_table("60", "sz_gem")
        old = self.bar("sz.300001", "2026-09-24", close="10.00")
        replacement = self.bar("sz.300001", "2026-09-24", close="12.34")
        db.upsert(self.conn, table, db.MINUTE_COLUMNS, [old])
        self.conn.commit()

        class OfflineConnection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        request = RefetchRequest(
            code="sz.300001", start="2026-09-24", end="2026-09-24")
        with patch("api.data_fetcher.BaostockConnectionManager", OfflineConnection), \
                patch("api.store.sync.fetch_kline_rows", return_value=[replacement]) as fetch:
            result = refetch_store_kline(request)

        self.assertEqual(result["rows"], 1)
        fetch.assert_called_once_with(
            "sz.300001", "2026-09-24", "2026-09-24", "60")
        row = self.conn.execute(
            f"SELECT close FROM {table} WHERE code='sz.300001'").fetchone()
        self.assertEqual(row["close"], "12.34")

    def test_local_scan_uses_sqlite_and_never_calls_baostock(self):
        code = "sz.300001"
        columns = ("code", "code_name", "ipoDate", "outDate", "type", "status",
                   "board", "updated_at")
        db.upsert(self.conn, "stock_basic", columns, [
            (code, "测试股份", "2020-01-01", "", "1", "1", "sz_gem",
             datetime.now().isoformat(timespec="seconds")),
        ])
        db.upsert(self.conn, "stock_industry",
                  ("code", "code_name", "industry", "industryClassification", "updateDate"),
                  [(code, "测试股份", "测试行业", "证监会行业分类", "2026-09-21")])

        start = datetime(2026, 9, 4)
        slots = ("103000000", "113000000", "140000000", "150000000")
        rows = []
        for offset in range(21):
            day = (start + timedelta(days=offset)).strftime("%Y-%m-%d")
            for slot in slots:
                rows.append((day, day.replace("-", "") + slot, code,
                             "10.00", "10.05", "9.95", "10.00", "1000", "10000", "3"))
        # 末端 K 线用普通 K 线模式锚定，历史价格全部位于箱体内。
        rows[-1] = ("2026-09-24", "20260924150000000", code,
                    "10.00", "10.20", "10.00", "10.10", "1000", "10100", "3")
        db.upsert(self.conn, db.kline_table("60", "sz_gem"), db.MINUTE_COLUMNS, rows)
        self.conn.commit()

        stocks = db.stock_list_with_kline(self.conn, "60", ["sz_gem"])
        rules = [{"id": "1", "params": HengpanRule(lookback=80).model_dump()}]
        stats = new_stats("2026-09-24", rules)
        params = {"max_workers": 2, "retry_attempts": 1}

        with patch("api.hengpan.scanner.ProcessPoolExecutor", ThreadPoolAsProcessPool), \
                patch("api.hengpan.scanner.fetch_kline",
                      side_effect=AssertionError("离线扫描不应调用联网 K 线入口")) as online_kline, \
                patch("api.hengpan.scanner.baostock_login",
                      side_effect=AssertionError("离线扫描不应登录 Baostock")) as online_login:
            began = time.perf_counter()
            found = scan_anchored_box(
                stocks, rules, params, "2026-09-24", stats,
                frequency="60", local_db_path=self.path,
            )
            elapsed_ms = (time.perf_counter() - began) * 1000

        online_kline.assert_not_called()
        online_login.assert_not_called()
        self.assertEqual([item["code"] for item in found], [code])
        self.assertEqual(stats["rules"]["1"]["analyzed"], 1)
        self.assertEqual(stats["rules"]["1"]["passed_full"], 1)
        self.assertLess(elapsed_ms, 1000)

    def test_local_scan_with_real_process_pool(self):
        """真实子进程应能直接打开只读 SQLite，并在退出后正常回收。"""
        code = "sz.300888"
        db.upsert(self.conn, "stock_basic",
                  ("code", "code_name", "ipoDate", "outDate", "type", "status",
                   "board", "updated_at"), [
                      (code, "进程测试", "2020-01-01", "", "1", "1", "sz_gem",
                       datetime.now().isoformat(timespec="seconds")),
                  ])
        rows = []
        for offset in range(3):
            day = (datetime(2026, 9, 22) + timedelta(days=offset)).strftime("%Y-%m-%d")
            for slot in ("103000000", "113000000", "140000000", "150000000"):
                rows.append((day, day.replace("-", "") + slot, code,
                             "10.00", "10.05", "9.95", "10.00", "1000", "10000", "3"))
        rows[-1] = ("2026-09-24", "20260924150000000", code,
                    "10.00", "10.20", "10.00", "10.10", "1000", "10100", "3")
        db.upsert(self.conn, db.kline_table("60", "sz_gem"), db.MINUTE_COLUMNS, rows)
        self.conn.commit()

        stocks = db.stock_list_with_kline(self.conn, "60", ["sz_gem"])
        rules = [{"id": "1", "params": HengpanRule(lookback=10).model_dump()}]
        stats = new_stats("2026-09-24", rules)
        found = scan_anchored_box(
            stocks, rules, {"max_workers": 1, "retry_attempts": 1},
            "2026-09-24", stats, frequency="60", local_db_path=self.path,
        )

        self.assertEqual([item["code"] for item in found], [code])
        self.assertEqual(stats["skipped"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
