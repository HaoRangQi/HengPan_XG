"""横盘扫描历史删除和清理策略测试。存储走 api/history/，这里验证薄封装的行为不变。"""
import os
import tempfile
import unittest
from unittest.mock import patch

from api.hengpan import history
from api.history import db, store


class HistoryCleanupTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        # 让薄封装落到临时库和临时 K 线目录
        patcher = patch.multiple(db,
                                 DB_PATH=os.path.join(self._temp.name, "history.db"),
                                 KLINE_DIR=os.path.join(self._temp.name, "scan_kline"))
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _snapshot(saved_at):
        return {"created_at": saved_at, "completed_at": saved_at, "status": "completed",
                "params": {"markets": ["sh_main"], "frequency": "60"},
                "results": [], "stats": {"rules": {}}}

    def _save(self, history_id, saved_at):
        history.save_history(history_id, self._snapshot(saved_at))
        # saved_at 由存储层按写入时刻记，测试要控制先后顺序就直接改表
        with db.open_db() as conn:
            conn.execute("UPDATE scan_run SET saved_at = ? WHERE run_id = ?",
                         (saved_at, history_id))
            conn.commit()

    def test_history_store_exposes_cleanup_operations(self):
        self.assertTrue(hasattr(history, "delete_history"))
        self.assertTrue(hasattr(history, "cleanup_histories"))

    def test_delete_history_removes_one_snapshot_and_reports_missing(self):
        self._save("keep", 100)
        self._save("remove", 200)

        self.assertTrue(history.delete_history("remove"))
        self.assertFalse(history.delete_history("remove"))
        self.assertIsNone(history.get_history("remove"))
        self.assertEqual([item["history_id"] for item in history.list_histories()], ["keep"])

    def test_cleanup_by_count_keeps_newest_records(self):
        for history_id, saved_at in (("old", 100), ("middle", 200), ("new", 300)):
            self._save(history_id, saved_at)

        result = history.cleanup_histories(keep_count=2)

        self.assertEqual(result, {"deleted": 1, "kept": 2})
        self.assertEqual([item["history_id"] for item in history.list_histories()],
                         ["new", "middle"])

    def test_cleanup_by_age_uses_saved_at_and_does_not_delete_recent_records(self):
        with patch.object(store.time, "time", return_value=1_000_000):
            self._save("old", 1_000_000 - 10 * 86400)
            self._save("new", 1_000_000 - 2 * 86400)

            result = history.cleanup_histories(keep_days=7)

            self.assertEqual(result, {"deleted": 1, "kept": 1})
            self.assertIsNone(history.get_history("old"))
            self.assertIsNotNone(history.get_history("new"))

    def test_cleanup_rejects_missing_or_invalid_policy(self):
        with self.assertRaises(ValueError):
            history.cleanup_histories()
        with self.assertRaises(ValueError):
            history.cleanup_histories(keep_count=0)
        with self.assertRaises(ValueError):
            history.cleanup_histories(keep_count=2, keep_days=7)

    def test_cleanup_only_touches_its_own_kind(self):
        """横盘-A 清理不该删掉横盘-U 和平台页的记录。"""
        self._save("hengpan-a", 100)
        store.save_run("hengpan_u", "hengpan-u", self._snapshot(100))
        store.save_run("platform_a", "platform-a", self._snapshot(100))

        history.cleanup_histories(keep_count=1)

        self.assertIsNotNone(store.get_run("hengpan-u"))
        self.assertIsNotNone(store.get_run("platform-a"))


if __name__ == "__main__":
    unittest.main()
