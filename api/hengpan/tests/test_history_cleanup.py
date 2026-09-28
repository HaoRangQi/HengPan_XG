"""横盘扫描历史删除和清理策略测试。"""
import tempfile
import unittest
from unittest.mock import patch

from api.hengpan import history


class HistoryCleanupTest(unittest.TestCase):
    def test_history_store_exposes_cleanup_operations(self):
        self.assertTrue(hasattr(history, "delete_history"))
        self.assertTrue(hasattr(history, "cleanup_histories"))

    def test_delete_history_removes_one_snapshot_and_reports_missing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(history, "_BASE_DIR", directory):
            history.save_history("keep", {"saved_at": 100, "results": [], "stats": {"rules": {}}})
            history.save_history("remove", {"saved_at": 200, "results": [], "stats": {"rules": {}}})

            self.assertTrue(history.delete_history("remove"))
            self.assertFalse(history.delete_history("remove"))
            self.assertIsNone(history.get_history("remove"))
            self.assertEqual([item["history_id"] for item in history.list_histories()], ["keep"])

    def test_cleanup_by_count_keeps_newest_records(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(history, "_BASE_DIR", directory):
            for history_id, saved_at in (("old", 100), ("middle", 200), ("new", 300)):
                history.save_history(history_id, {"saved_at": saved_at, "results": [], "stats": {"rules": {}}})

            result = history.cleanup_histories(keep_count=2)

            self.assertEqual(result, {"deleted": 1, "kept": 2})
            self.assertEqual([item["history_id"] for item in history.list_histories()], ["new", "middle"])

    def test_cleanup_by_age_uses_saved_at_and_does_not_delete_recent_records(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(history, "_BASE_DIR", directory), \
                patch.object(history.time, "time", return_value=1_000_000):
            history.save_history("old", {"saved_at": 1_000_000 - 10 * 86400, "results": [], "stats": {"rules": {}}})
            history.save_history("new", {"saved_at": 1_000_000 - 2 * 86400, "results": [], "stats": {"rules": {}}})

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


if __name__ == "__main__":
    unittest.main()
