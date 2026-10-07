"""平台期扫描本地数据源与旧版兼容契约。"""
import inspect
import asyncio
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch

from pydantic import ValidationError

from api.config import ScanConfig
from api import index
from api.index import ScanConfigRequest, build_result_stock
from api.platform_scanner import scan_stocks
from api.platform_scan_source import PlatformScanSource
from api.store import db
from fastapi import BackgroundTasks


class PlatformSourceContractTest(unittest.TestCase):
    def test_request_keeps_legacy_default_and_accepts_explicit_local_source(self):
        self.assertEqual(ScanConfigRequest().model_dump().get("data_source"), "baostock")
        self.assertEqual(ScanConfigRequest(data_source="local").data_source, "local")
        with self.assertRaises(ValidationError):
            ScanConfigRequest(data_source="unknown")

    def test_scanner_supports_an_explicit_local_database(self):
        parameters = inspect.signature(scan_stocks).parameters
        self.assertIn("local_db_path", parameters)
        self.assertIn("end_date", parameters)

    def test_local_source_prepares_stock_pool_without_network(self):
        self.assertTrue(hasattr(index, "prepare_platform_scan_source"))
        if not hasattr(index, "prepare_platform_scan_source"):
            return

        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(path)
        conn = db.connect(path)
        try:
            db.upsert(conn, "stock_basic",
                      ("code", "code_name", "ipoDate", "outDate", "type", "status",
                       "board", "updated_at"), [
                          ("sz.300001", "测试股份", "2020-01-01", "", "1", "1",
                           "sz_gem", "2026-09-28T10:00:00"),
                      ])
            db.upsert(conn, "stock_industry",
                      ("code", "code_name", "industry", "industryClassification", "updateDate"),
                      [("sz.300001", "测试股份", "测试行业", "证监会行业分类", "2026-09-28")])
            db.upsert(conn, db.kline_table("60", "sz_gem"), db.MINUTE_COLUMNS, [
                ("2026-09-24", "20260924150000000", "sz.300001",
                 "10", "10.1", "9.9", "10", "1000", "10000", "3"),
            ])
            conn.commit()
        finally:
            conn.close()

        try:
            with patch("api.platform_scan_source.fetch_stock_basics",
                       side_effect=AssertionError("本地股票池不应联网")) as stock_basics, \
                    patch("api.platform_scan_source.fetch_industry_data",
                          side_effect=AssertionError("本地行业信息不应联网")) as industry:
                source = index.prepare_platform_scan_source(
                    "local", ["sz_gem"], "60", False, db_path=path)
            stock_basics.assert_not_called()
            industry.assert_not_called()
            self.assertEqual([stock["code"] for stock in source.stock_list], ["sz.300001"])
            self.assertEqual(source.end_date, "2026-09-24")
            self.assertEqual(source.local_db_path, path)
        finally:
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(path + suffix):
                    os.unlink(path + suffix)

    def test_async_endpoint_wires_local_source_into_scanner(self):
        background = BackgroundTasks()
        source = PlatformScanSource(
            "local",
            [{"code": "sz.300001", "name": "测试股份", "industry": "测试行业"}],
            "60",
            "/tmp/platform-local-test.db",
            "2026-09-24",
        )
        request = ScanConfigRequest(
            data_source="local",
            frequency="60",
            markets=["sz_gem"],
            use_fundamental_filter=False,
        )

        with patch.object(index, "prepare_platform_scan_source", return_value=source) as prepare, \
                patch.object(index, "scan_stocks", return_value=[]) as scan, \
                patch.object(index, "save_scan_history") as save:
            response = asyncio.run(index.start_scan(request, background))
            asyncio.run(background())

        prepare.assert_called_once_with("local", ["sz_gem"], "60", False)
        self.assertEqual(scan.call_args.kwargs["frequency"], "60")
        self.assertEqual(scan.call_args.kwargs["local_db_path"], source.local_db_path)
        self.assertEqual(scan.call_args.kwargs["end_date"], source.end_date)
        self.assertIn("本地", response.message)
        self.assertEqual(save.call_args.args[1]["data_source"], "local")

    def test_local_result_keeps_one_timestamp_and_normalises_nan_fields(self):
        result = build_result_stock({
            "code": "sz.300001",
            "name": "测试股份",
            "industry": "测试行业",
            "selection_reasons": {10: "满足平台期"},
            "kline_data": [{
                "date": "2026-09-24 15:00:00",
                "time": "2026-09-24 15:00:00",
                "open": 10.0,
                "high": 10.1,
                "low": 9.9,
                "close": 10.0,
                "volume": 1000.0,
                "turn": float("nan"),
            }],
        })

        self.assertEqual(result.kline_data[0].date, "2026-09-24 15:00:00")
        self.assertIsNone(result.kline_data[0].turn)


class PlatformLocalScanTest(unittest.TestCase):
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

    def _seed_bars(self, code):
        rows = []
        moments = [datetime(2026, 9, day, hour, minute) for day in (22, 23, 24)
                   for hour, minute in ((10, 30), (11, 30), (14, 0), (15, 0))]
        for moment in moments:
            day = moment.strftime("%Y-%m-%d")
            raw_time = moment.strftime("%Y%m%d%H%M%S") + "000"
            rows.append((day, raw_time, code, "10", "10.1", "9.9", "10", "1000", "10000", "3"))
        db.upsert(self.conn, db.kline_table("60", "sz_gem"), db.MINUTE_COLUMNS, rows)
        self.conn.commit()

    @staticmethod
    def _config():
        return ScanConfig(
            windows=[10],
            use_box_detection=False,
            use_volume_analysis=False,
            use_low_position=False,
            use_rapid_decline_detection=False,
            use_fundamental_filter=False,
            expected_count=None,
            max_workers=1,
        )

    def test_local_scan_skips_symbol_behind_selected_universe_endpoint(self):
        self._seed_bars("sz.300001")
        self._seed_bars("sz.300002")
        table = db.kline_table("60", "sz_gem")
        self.conn.execute(f"DELETE FROM {table} WHERE code=? AND time=?",
                          ("sz.300001", "20260924150000000"))
        self.conn.commit()
        progress = []
        with patch("api.platform_scanner.ProcessPoolExecutor", ThreadPoolExecutor):
            results = scan_stocks(
                [{"code": code, "name": code} for code in ("sz.300001", "sz.300002")],
                self._config(), frequency="60", local_db_path=self.path, end_date="2026-09-24",
                update_progress=lambda **kw: progress.append(kw))
        self.assertEqual([item["code"] for item in results], ["sz.300002"])
        self.assertIn("过期 1", progress[-1]["message"])

    def test_local_scan_skips_intraday_gap_and_reports_reason(self):
        self._seed_bars("sz.300001")
        table = db.kline_table("60", "sz_gem")
        self.conn.execute(f"DELETE FROM {table} WHERE time=?", ("20260923103000000",))
        self.conn.commit()
        progress = []
        with patch("api.platform_scanner.ProcessPoolExecutor", ThreadPoolExecutor):
            results = scan_stocks([{"code": "sz.300001", "name": "demo"}], self._config(),
                                 frequency="60", local_db_path=self.path, end_date="2026-09-24",
                                 update_progress=lambda **kw: progress.append(kw))
        self.assertEqual(results, [])
        self.assertIn("缺口 1", progress[-1]["message"])

    def test_local_scan_reads_sqlite_without_any_baostock_call(self):
        parameters = inspect.signature(scan_stocks).parameters
        self.assertIn("local_db_path", parameters)
        if "local_db_path" not in parameters:
            return

        code = "sz.300001"
        self._seed_bars(code)
        config = self._config()
        progress = []

        with patch("api.platform_scanner.ProcessPoolExecutor", ThreadPoolExecutor), \
                patch("api.platform_scanner.fetch_kline_data",
                      side_effect=AssertionError("本地扫描不应调用联网 K 线入口")) as online_kline, \
                patch("api.platform_scanner.baostock_login",
                      side_effect=AssertionError("本地扫描不应登录 Baostock")) as online_login:
            scan_stocks(
                [{"code": code, "name": "测试股份", "industry": "测试行业"}],
                config,
                update_progress=lambda **fields: progress.append(fields),
                frequency="60",
                local_db_path=self.path,
                end_date="2026-09-24",
            )

        online_kline.assert_not_called()
        online_login.assert_not_called()
        self.assertTrue(progress)
        self.assertEqual(progress[-1]["scanned"], 1)

    def test_local_scan_works_with_real_process_pool(self):
        code = "sz.300001"
        self._seed_bars(code)

        results = scan_stocks(
            [{"code": code, "name": "测试股份", "industry": "测试行业"}],
            self._config(),
            frequency="60",
            local_db_path=self.path,
            end_date="2026-09-24",
        )

        self.assertEqual([item["code"] for item in results], [code])


if __name__ == "__main__":
    unittest.main()
