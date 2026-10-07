"""Restart and failed-history recovery against real temporary SQLite caches."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from api.history import db, store
from api.task_manager import TaskExtras, TaskStatus, task_manager


class TaskRecoveryReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch('api.task_results.ROOT', str(root / 'cache')),
                        patch.object(task_manager, '_tasks', {}),
                        patch.object(db, 'DB_PATH', str(root / 'history.db')),
                        patch.object(db, 'KLINE_DIR', str(root / 'klines'))]
        for item in self.patches:
            item.start()
        self.manager = task_manager

    def tearDown(self):
        for task in list(self.manager._tasks.values()):
            task.close()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def task(self):
        ident = self.manager.create_task()
        TaskExtras('platform_a')[ident] = {'frequency': '60', 'windows': [20]}
        self.manager.append_streamed(ident, [{'code': 'A', 'kline_data': [
            {'date': '2026-10-01 10:30:00', 'close': 10.},
            {'date': '2026-10-01 11:30:00', 'close': 11.}]}])
        return self.manager.get_task(ident)

    def restart(self):
        self.manager._tasks.clear()  # Simulate process loss without deleting durable caches.
        self.manager.recover()

    def test_restart_pending_interrupts_and_keeps_unsaved_klines(self):
        task = self.task()
        ident = task.task_id
        self.restart()
        restored = self.manager.get_task(ident)
        self.assertEqual(restored.status, TaskStatus.FAILED)
        self.assertFalse(restored.history_saved)
        self.assertEqual(len(restored.kline('A')), 2)
        self.manager.clean_old_tasks(max_age_seconds=0, max_completed=0)
        self.assertIs(self.manager.get_task(ident), restored)

    def test_history_failure_restarts_then_retries_without_losing_klines(self):
        task = self.task()
        ident = task.task_id
        self.manager.finish_results(ident, [{'code': 'A'}])
        self.manager.update_task(ident, status=TaskStatus.COMPLETED)
        with patch.object(store, '_write_klines', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.manager.save_pending_history(ident)
        self.assertFalse(task.history_saved)
        self.assertIn('disk full', task.history_error)
        self.restart()
        self.manager.save_pending_history(ident)
        self.assertIsNotNone(store.get_run(ident, with_hits=False))
        self.assertEqual(len(store.get_kline(ident, 'A')), 2)
        self.assertTrue(self.manager.get_task(ident).history_saved)

    def test_failed_history_and_failed_error_journal_never_claim_saved(self):
        task = self.task()
        self.manager.update_task(task.task_id, status=TaskStatus.FAILED)
        with patch.object(store, '_write_klines', side_effect=OSError('disk full')), \
             patch.object(task, 'checkpoint', side_effect=OSError('journal full')):
            with self.assertRaises(OSError):
                self.manager.save_pending_history(task.task_id)
        self.assertFalse(task.history_saved)
        self.assertIsNone(store.get_run(task.task_id, with_hits=False))
        self.assertEqual(len(task.kline('A')), 2)

    def test_unreadable_journal_preserves_cache_files(self):
        task = self.task()
        directory = Path(task._cache.directory)
        (directory / 'task.json').write_text('{broken')
        self.restart()
        self.assertTrue((directory / 'results.db').exists())
        self.assertIsNone(self.manager.get_task(task.task_id))

    def test_interrupted_results_survive_two_restarts(self):
        ident = self.task().task_id
        self.restart()
        self.restart()
        restored = self.manager.get_task(ident)
        self.assertEqual(restored.result_page()['total'], 1)
        self.manager.save_pending_history(ident)
        self.assertEqual(store.get_run(ident)['result_count'], 1)
        self.assertEqual(len(store.get_kline(ident, 'A')), 2)

    def test_checkpoint_preserves_numeric_metadata_types(self):
        import numpy as np
        task = self.task()
        task.metadata['platform_a']['stats'] = {'analyzed': np.int64(42)}
        task.checkpoint()
        ident = task.task_id
        self.restart()
        value = self.manager.get_task(ident).metadata['platform_a']['stats']['analyzed']
        self.assertEqual(value, 42)
        self.assertIsInstance(value, int)
