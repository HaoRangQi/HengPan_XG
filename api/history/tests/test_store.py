"""扫描历史库的读写测试：四个页面格式互转、筛选分页、去重、清理、按需取 K 线。"""
import os
import tempfile
import unittest

from api.history import db, store


def _hengpan_a_snapshot(scan_date="2026-09-24", frequency="60", codes=("sh.600519",)):
    return {
        "task_id": "ignored",
        "status": "completed",
        "message": "扫描完成",
        "created_at": 1000.0,
        "completed_at": 1100.0,
        "scan_date": scan_date,
        "frequency": frequency,
        "params": {"markets": ["sh_main"], "frequency": frequency, "scan_date": scan_date,
                   "rules": [{"box_type": "tolerant", "box_height": 0.02}]},
        "rules": [{"id": "1", "params": {"box_type": "tolerant", "box_height": 0.02}}],
        "stats": {"rules": {"1": {"analyzed": 100, "passed_full": 2}}},
        "scanned": 100, "total": 100, "found": len(codes),
        "results": [{
            "code": code, "name": "贵州茅台", "industry": "白酒", "is_st": False,
            "date": scan_date, "close": 1500.5, "amplitude": 0.01,
            "matches": {"1": {"passed_full": True, "passed_body": True, "mode": "tolerant"},
                        "2": {"passed_full": False, "passed_body": True, "mode": "tolerant"}},
            "kline_data": [{"date": "2026-09-24", "close": 1500.5}],
        } for code in codes],
    }


def _platform_a_snapshot():
    return {
        "status": "completed", "message": "扫描完成", "created_at": 2000.0,
        "completed_at": 2100.0, "frequency": "d", "data_source": "baostock",
        "config": {"windows": [80], "frequency": "d", "markets": ["sh_main"]},
        "parameters": {"windows": [80], "frequency": "d", "markets": ["sh_main"]},
        "windows": [80], "scanned": 50, "total": 50, "found": 1,
        "results": [{
            "code": "sz.000001", "name": "平安银行", "industry": "银行",
            "selection_reasons": {"80": "80日平台期"},
            "mark_lines": [{"text": "支撑位", "value": 11.3}],
            "kline_data": [{"date": "2026-09-24", "close": 11.4}],
        }],
    }


def _hengpan_u_snapshot():
    return {
        "status": "completed", "message": "扫描完成", "created_at": 3000.0,
        "completed_at": 3100.0, "scan_date": "2026-09-28", "frequency": "1h",
        "params": {"categories": ["perpetual"], "frequency": "1h",
                   "rules": [{"box_type": "fixed", "box_height": 0.01}]},
        "rules": [{"id": "1", "params": {"box_type": "fixed"}}],
        "stats": {"rules": {"1": {"analyzed": 300, "passed_full": 1}}},
        "scanned": 300, "total": 300, "found": 1,
        "results": [{
            "symbol": "BTCUSDT", "base_asset": "BTC", "category": "perpetual",
            "category_label": "加密永续", "quote_volume": 1e9, "last_price": 60000.0,
            "close": 60000.0, "amplitude": 0.004,
            "matches": {"1": {"passed_full": True, "passed_body": True}},
            "kline_data": [{"date": "2026-09-28 10:00", "close": 60000.0}],
        }],
    }


class HistoryStoreTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.kline_dir = os.path.join(self._temp.name, "scan_kline")
        self.conn = db.connect(os.path.join(self._temp.name, "history.db"))
        self.addCleanup(self.conn.close)

    def save(self, kind, run_id, snapshot):
        return store.save_run(kind, run_id, snapshot, conn=self.conn,
                              kline_base_dir=self.kline_dir)

    def test_hengpan_a_round_trip_preserves_original_result_fields(self):
        self.save("hengpan_a", "run-1", _hengpan_a_snapshot())

        payload = store.get_run("run-1", conn=self.conn)
        self.assertEqual(payload["kind"], "hengpan_a")
        self.assertEqual(payload["market"], "a")
        self.assertEqual(payload["frequency"], "60")
        self.assertEqual(payload["scan_date"], "2026-09-24")
        self.assertEqual(payload["params"]["markets"], ["sh_main"])
        self.assertEqual(payload["stats"]["rules"]["1"]["passed_full"], 2)

        hit = payload["results"][0]
        self.assertEqual(hit["code"], "sh.600519")
        self.assertEqual(hit["name"], "贵州茅台")
        self.assertEqual(hit["industry"], "白酒")
        self.assertIs(hit["is_st"], False)
        # matches 原样还原，前端的规则组分栏逻辑不用改
        self.assertEqual(sorted(hit["matches"]), ["1", "2"])
        # 命中组数直接给出，就是「该标的命中了多少条规则」
        self.assertEqual(hit["rule_count"], 2)
        self.assertEqual(sorted(hit["matched_rules"]), ["1", "2"])
        # 详情不带 K 线，看图另取
        self.assertEqual(hit["kline_data"], [])

    def test_kline_is_stored_per_code_and_read_on_demand(self):
        self.save("hengpan_a", "run-1", _hengpan_a_snapshot())

        kline = store.get_kline("run-1", "sh.600519", self.kline_dir)
        self.assertEqual(kline, [{"date": "2026-09-24", "close": 1500.5}])
        self.assertIsNone(store.get_kline("run-1", "sh.999999", self.kline_dir))
        # 体积记在 run 上，供容量提醒使用
        self.assertGreater(store.get_run("run-1", conn=self.conn)["kline_bytes"], 0)

    def test_platform_a_windows_become_matched_rules(self):
        self.save("platform_a", "run-p", _platform_a_snapshot())

        payload = store.get_run("run-p", conn=self.conn)
        self.assertEqual(payload["frequency"], "d")
        self.assertEqual(payload["market"], "a")
        # 页面独有字段留在 extra 里，读回时合并回顶层
        self.assertEqual(payload["data_source"], "baostock")
        self.assertEqual(payload["windows"], [80])
        hit = payload["results"][0]
        self.assertEqual(hit["matched_rules"], ["80"])
        self.assertEqual(hit["rule_count"], 1)
        self.assertEqual(hit["mark_lines"][0]["text"], "支撑位")
        # 老接口同时给 results 和 result
        self.assertEqual(payload["result"], payload["results"])

    def test_crypto_snapshot_keeps_symbol_key_and_maps_to_crypto_market(self):
        self.save("hengpan_u", "run-u", _hengpan_u_snapshot())

        payload = store.get_run("run-u", conn=self.conn)
        self.assertEqual(payload["market"], "crypto")
        self.assertEqual(payload["frequency"], "1h")
        hit = payload["results"][0]
        self.assertEqual(hit["symbol"], "BTCUSDT")
        self.assertEqual(hit["category_label"], "加密永续")
        self.assertNotIn("code", hit)

    def test_list_filters_by_market_and_intraday_frequency(self):
        self.save("hengpan_a", "intraday", _hengpan_a_snapshot(frequency="60"))
        self.save("hengpan_a", "daily", _hengpan_a_snapshot(frequency="d"))
        self.save("hengpan_u", "crypto", _hengpan_u_snapshot())

        intraday = store.list_runs(intraday_only=True, conn=self.conn)
        self.assertEqual(sorted(item["run_id"] for item in intraday["histories"]),
                         ["crypto", "intraday"])

        a_only = store.list_runs(market="a", intraday_only=True, conn=self.conn)
        self.assertEqual([item["run_id"] for item in a_only["histories"]], ["intraday"])

        crypto_only = store.list_runs(market="crypto", conn=self.conn)
        self.assertEqual([item["run_id"] for item in crypto_only["histories"]], ["crypto"])

        # 显式给周期时忽略 intraday_only
        daily = store.list_runs(frequency="d", intraday_only=True, conn=self.conn)
        self.assertEqual([item["run_id"] for item in daily["histories"]], ["daily"])

    def test_list_filters_by_code_and_date_range(self):
        self.save("hengpan_a", "has-code", _hengpan_a_snapshot(codes=("sh.600519",)))
        self.save("hengpan_a", "other-code", _hengpan_a_snapshot(codes=("sz.000001",)))
        self.save("hengpan_a", "older", _hengpan_a_snapshot(scan_date="2026-08-01"))

        by_code = store.list_runs(code="sh.600519", conn=self.conn)
        self.assertEqual(sorted(item["run_id"] for item in by_code["histories"]),
                         ["has-code", "older"])

        ranged = store.list_runs(date_from="2026-09-01", conn=self.conn)
        self.assertNotIn("older", [item["run_id"] for item in ranged["histories"]])

    def test_list_paginates_and_pins_stay_on_top(self):
        for index in range(5):
            self.save("hengpan_a", f"run-{index}", _hengpan_a_snapshot())
        store.update_run("run-0", pinned=True, conn=self.conn)

        first = store.list_runs(page=1, page_size=2, conn=self.conn)
        self.assertEqual(first["total"], 5)
        self.assertEqual(first["page_size"], 2)
        self.assertEqual(len(first["histories"]), 2)
        self.assertEqual(first["histories"][0]["run_id"], "run-0")
        self.assertTrue(first["histories"][0]["pinned"])

        second = store.list_runs(page=2, page_size=2, conn=self.conn)
        self.assertEqual(len(second["histories"]), 2)
        self.assertFalse(set(item["run_id"] for item in first["histories"]) &
                         set(item["run_id"] for item in second["histories"]))

    def test_same_params_are_flagged_as_duplicates(self):
        self.save("hengpan_a", "first", _hengpan_a_snapshot())
        self.save("hengpan_a", "second", _hengpan_a_snapshot())
        self.save("hengpan_a", "different", _hengpan_a_snapshot(scan_date="2026-08-01"))

        listed = {item["run_id"]: item for item in
                  store.list_runs(conn=self.conn)["histories"]}
        self.assertEqual(listed["first"]["params_hash"], listed["second"]["params_hash"])
        self.assertEqual(listed["first"]["duplicate_count"], 2)
        self.assertNotEqual(listed["different"]["params_hash"], listed["first"]["params_hash"])
        self.assertEqual(listed["different"]["duplicate_count"], 1)

    def test_failed_run_is_recorded_with_message_and_no_hits(self):
        self.save("hengpan_a", "bad", {
            "status": "failed", "message": "扫描失败：无法连接数据源",
            "error": "ConnectionError", "created_at": 1.0, "frequency": "60",
            "params": {"markets": ["sh_main"]}, "results": [],
        })

        payload = store.get_run("bad", conn=self.conn)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["found"], 0)
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["error"], "ConnectionError")
        self.assertIn("无法连接数据源", payload["message"])

    def test_rewriting_same_run_replaces_hits_and_keeps_note(self):
        self.save("hengpan_a", "run-1", _hengpan_a_snapshot(codes=("sh.600519", "sz.000001")))
        store.update_run("run-1", note="重点关注", pinned=True, conn=self.conn)

        self.save("hengpan_a", "run-1", _hengpan_a_snapshot(codes=("sh.600519",)))

        payload = store.get_run("run-1", conn=self.conn)
        self.assertEqual([hit["code"] for hit in payload["results"]], ["sh.600519"])
        # 重写不该抹掉用户手写的备注和置顶
        self.assertEqual(payload["note"], "重点关注")
        self.assertTrue(payload["pinned"])
        # 旧标的的 K 线文件也要跟着清掉
        self.assertIsNone(store.get_kline("run-1", "sz.000001", self.kline_dir))

    def test_delete_removes_hits_and_kline_files(self):
        self.save("hengpan_a", "run-1", _hengpan_a_snapshot())

        self.assertTrue(store.delete_run("run-1", conn=self.conn,
                                         kline_base_dir=self.kline_dir))
        self.assertFalse(store.delete_run("run-1", conn=self.conn,
                                          kline_base_dir=self.kline_dir))
        self.assertIsNone(store.get_run("run-1", conn=self.conn))
        self.assertEqual(store.hit_codes("run-1", conn=self.conn), [])
        self.assertIsNone(store.get_kline("run-1", "sh.600519", self.kline_dir))

    def test_cleanup_by_count_keeps_newest_and_skips_pinned(self):
        for index in range(4):
            self.save("hengpan_a", f"run-{index}", _hengpan_a_snapshot())
            self.conn.execute("UPDATE scan_run SET saved_at = ? WHERE run_id = ?",
                              (100.0 + index, f"run-{index}"))
        self.conn.commit()
        store.update_run("run-0", pinned=True, conn=self.conn)

        result = store.cleanup_runs(keep_count=2, conn=self.conn,
                                    kline_base_dir=self.kline_dir)

        self.assertEqual(result["deleted"], 1)
        remaining = sorted(item["run_id"] for item in
                           store.list_runs(conn=self.conn)["histories"])
        # run-0 置顶豁免，run-1 是非置顶里最旧的一条被删
        self.assertEqual(remaining, ["run-0", "run-2", "run-3"])

    def test_cleanup_zero_clears_all_runs_hits_and_kline_files(self):
        for kind in ("hengpan_a", "hengpan_u", "platform_a", "platform_u"):
            self.save(kind, kind, _hengpan_a_snapshot())
        before = store.overview(conn=self.conn)
        self.assertEqual(before["runs"], 4)
        self.assertGreater(before["hits"], 0)
        self.assertGreater(before["kline_bytes"], 0)

        preview = store.cleanup_runs(keep_count=0, dry_run=True, conn=self.conn,
                                     kline_base_dir=self.kline_dir)
        self.assertEqual(preview, {"deleted": 4, "kept": 0})
        self.assertEqual(store.overview(conn=self.conn), before)
        self.assertTrue(os.listdir(self.kline_dir))

        result = store.cleanup_runs(keep_count=0, conn=self.conn, kline_base_dir=self.kline_dir)
        self.assertEqual(result, preview)
        summary = store.overview(conn=self.conn)
        self.assertEqual((summary["runs"], summary["hits"], summary["kline_bytes"]), (0, 0, 0))
        self.assertEqual(os.listdir(self.kline_dir), [])
        self.assertEqual(store.cleanup_runs(keep_count=0, conn=self.conn,
                                            kline_base_dir=self.kline_dir),
                         {"deleted": 0, "kept": 0})

    def test_cleanup_zero_respects_scope_and_pinned_protection(self):
        for key in ("keep_count", "keep_days", "max_kline_bytes"):
            with self.subTest(key=key):
                self.save("hengpan_a", "remove", _hengpan_a_snapshot())
                self.save("hengpan_a", "empty", {"results": []})
                self.save("hengpan_a", "pinned", _hengpan_a_snapshot())
                self.save("hengpan_u", "other", _hengpan_u_snapshot())
                store.update_run("pinned", pinned=True, conn=self.conn)
                # 0 表示清空；不能因时钟偏差或没有 K 线快照而留下记录。
                self.conn.execute("UPDATE scan_run SET saved_at = 99999999999")
                self.conn.commit()

                policy = {key: 0, "kind": "hengpan_a", "conn": self.conn,
                          "kline_base_dir": self.kline_dir}
                preview = store.cleanup_runs(**policy, dry_run=True)
                self.assertEqual(preview, {"deleted": 2, "kept": 1})
                self.assertIsNotNone(store.get_run("remove", conn=self.conn))
                result = store.cleanup_runs(**policy)
                self.assertEqual(result, preview)
                for run_id in ("remove", "empty"):
                    self.assertIsNone(store.get_run(run_id, conn=self.conn))
                    self.assertEqual(store.hit_codes(run_id, conn=self.conn), [])
                    self.assertFalse(os.path.exists(os.path.join(self.kline_dir, run_id)))
                for run_id, code in (("pinned", "sh.600519"), ("other", "BTCUSDT")):
                    self.assertIsNotNone(store.get_run(run_id, conn=self.conn))
                    self.assertTrue(store.get_kline(run_id, code, self.kline_dir))

    def test_cleanup_by_days_uses_saved_at(self):
        self.save("hengpan_a", "old", _hengpan_a_snapshot())
        self.save("hengpan_a", "new", _hengpan_a_snapshot(scan_date="2026-09-25"))
        self.conn.execute("UPDATE scan_run SET saved_at = saved_at - ? WHERE run_id = 'old'",
                          (10 * 86400,))
        self.conn.commit()

        result = store.cleanup_runs(keep_days=7, conn=self.conn,
                                    kline_base_dir=self.kline_dir)

        self.assertEqual(result["deleted"], 1)
        self.assertIsNone(store.get_run("old", conn=self.conn))
        self.assertIsNotNone(store.get_run("new", conn=self.conn))

    def test_cleanup_by_total_kline_bytes_drops_oldest_over_budget(self):
        for index in range(3):
            self.save("hengpan_a", f"run-{index}", _hengpan_a_snapshot())
            self.conn.execute(
                "UPDATE scan_run SET saved_at = ?, kline_bytes = 100 WHERE run_id = ?",
                (100.0 + index, f"run-{index}"))
        self.conn.commit()

        result = store.cleanup_runs(max_kline_bytes=250, conn=self.conn,
                                    kline_base_dir=self.kline_dir)

        self.assertEqual(result["deleted"], 1)
        self.assertIsNone(store.get_run("run-0", conn=self.conn))

    def test_cleanup_rejects_missing_or_multiple_policies(self):
        with self.assertRaises(ValueError):
            store.cleanup_runs(conn=self.conn)
        with self.assertRaises(ValueError):
            store.cleanup_runs(keep_count=2, keep_days=7, conn=self.conn)
        with self.assertRaises(ValueError):
            store.cleanup_runs(keep_count=-1, conn=self.conn)
        for policy in ({"keep_days": -1}, {"max_kline_bytes": -1}, {"keep_count": False}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                store.cleanup_runs(**policy, conn=self.conn)

    def test_overview_totals_by_kind(self):
        self.save("hengpan_a", "run-a", _hengpan_a_snapshot())
        self.save("platform_a", "run-p", _platform_a_snapshot())

        summary = store.overview(conn=self.conn)
        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["hits"], 2)
        self.assertGreater(summary["kline_bytes"], 0)
        labels = {entry["kind"]: entry["kind_label"] for entry in summary["by_kind"]}
        self.assertEqual(labels, {"hengpan_a": "横盘-A", "platform_a": "平台-A"})

    def test_code_appearances_span_runs(self):
        self.save("hengpan_a", "run-1", _hengpan_a_snapshot(scan_date="2026-09-23"))
        self.save("hengpan_a", "run-2", _hengpan_a_snapshot(scan_date="2026-09-24"))
        self.save("hengpan_a", "run-3", _hengpan_a_snapshot(codes=("sz.000001",)))

        found = store.code_appearances("sh.600519", conn=self.conn)
        self.assertEqual(found["run_count"], 2)
        self.assertEqual(sorted(item["run_id"] for item in found["appearances"]),
                         ["run-1", "run-2"])
        self.assertEqual(found["appearances"][0]["rule_count"], 2)
        self.assertEqual(found["appearances"][0]["kind_label"], "横盘-A")

        self.assertEqual(store.code_appearances("sh.000000", conn=self.conn)["run_count"], 0)

    def test_update_run_returns_none_for_missing_run(self):
        self.assertIsNone(store.update_run("nope", note="x", conn=self.conn))


if __name__ == "__main__":
    unittest.main()
