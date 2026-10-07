"""Independent regressions for bounded history saves and authoritative results."""
import glob
import os
import tempfile
import unittest
from api.history import db, store


class HistoryStreamingReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.conn = db.connect(os.path.join(self.temp.name, 'history.db'))
        self.addCleanup(self.conn.close)
        self.addCleanup(self.temp.cleanup)

    def save(self, snapshot):
        return store.save_run('platform_a', 'review', snapshot, conn=self.conn,
                              kline_base_dir=self.temp.name)

    def test_empty_final_results_do_not_fall_back_to_candidates(self):
        self.save({'results': [], 'result': [{'code': 'REJECTED'}]})
        self.assertEqual(store.get_run('review', conn=self.conn)['results'], [])

    def test_history_writes_each_kline_before_consuming_next_hit(self):
        def results():
            yield {'code': 'A', 'kline_data': [{'date': '2026-10-01', 'close': 10.}]}
            staged = glob.glob(os.path.join(self.temp.name, '.pending-*', 'review', 'A.json'))
            self.assertTrue(staged, 'save_run retains all decoded K-lines before writing any')
            yield {'code': 'B', 'kline_data': [{'date': '2026-10-02', 'close': 11.}]}
        self.save({'results': results()})
        saved = store.get_run('review', conn=self.conn)
        self.assertEqual(saved['result_count'], 2)
        self.assertEqual(saved['scan_date'], '2026-10-02')

    def test_later_invalid_hit_preserves_old_database_and_kline(self):
        self.save({'results': [{'code': 'A', 'kline_data': [{'close': 1.}]}]})
        with self.assertRaises(ValueError):
            self.save({'results': [{'code': 'A', 'kline_data': [{'close': 2.}]}, {'code': '../bad'}]})
        self.assertEqual(store.get_kline('review', 'A', self.temp.name), [{'close': 1.}])
        self.assertEqual(len(store.get_run('review', conn=self.conn)['results']), 1)

    def test_history_result_page_does_not_fetch_all_hits(self):
        self.save({'results': [{'code': str(i)} for i in range(230)]})
        queries = []
        self.conn.set_trace_callback(queries.append)
        page = store.result_page('review', offset=100, limit=50, conn=self.conn)
        self.assertEqual(page['total'], 230)
        self.assertEqual(page['next_offset'], 150)
        self.assertEqual([row['code'] for row in page['results']], [str(i) for i in range(100, 150)])
        self.assertTrue(any('LIMIT 50 OFFSET 100' in query for query in queries))


class ScanRetentionReviewTests(unittest.TestCase):
    def test_platform_callback_can_release_full_kline_payload(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        from api.config import ScanConfig
        from api.platform_scanner import scan_stocks
        from api.tests.test_data_quality import frame
        data = frame(40, 'D')
        config = ScanConfig(windows=[20], use_low_position=False, use_volume_analysis=False,
                            use_box_detection=False, expected_count=None, max_workers=1)
        captured = []
        def cached(stock):
            captured.append(len(stock['kline_data']))
            return {key: value for key, value in stock.items() if key != 'kline_data'}
        with patch('api.platform_scanner.ProcessPoolExecutor', ThreadPoolExecutor), \
             patch('api.platform_scanner.baostock_login'), \
             patch('api.platform_scanner.fetch_kline_data', return_value=data):
            found = scan_stocks([{'code': 'sh.600000', 'name': 'demo'}], config,
                                end_date=data['date'].iloc[-1][:10], on_found=cached)
        self.assertEqual(captured, [40])
        self.assertNotIn('kline_data', found[0])


class TaskCapacityReviewTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        from api.task_manager import task_manager
        self.manager = task_manager
        self.temp = tempfile.TemporaryDirectory()
        self.root_patch = patch('api.task_results.ROOT', self.temp.name)
        self.tasks_patch = patch.object(task_manager, '_tasks', {})
        self.root_patch.start()
        self.tasks_patch.start()

    def tearDown(self):
        for task in list(self.manager._tasks.values()):
            task.close()
        self.tasks_patch.stop()
        self.root_patch.stop()
        self.temp.cleanup()

    def test_ninth_active_task_is_rejected(self):
        from fastapi import HTTPException
        for _ in range(8):
            self.manager.create_task()
        with self.assertRaises(HTTPException) as error:
            self.manager.create_task()
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(len(self.manager._tasks), 8)

    def test_unsaved_terminal_tasks_are_preserved_and_cap_new_tasks(self):
        from fastapi import HTTPException
        from api.task_manager import TaskStatus
        ids = []
        for _ in range(8):
            ident = self.manager.create_task()
            ids.append(ident)
            task = self.manager.get_task(ident)
            task.history_required = True
            task.update(status=TaskStatus.FAILED)
            task.completed_at = 1
        self.manager.clean_old_tasks(max_age_seconds=1, max_completed=1)
        self.assertEqual(set(self.manager._tasks), set(ids))
        with self.assertRaises(HTTPException):
            self.manager.create_task()

    def test_completed_retention_cap_removes_cache_directories(self):
        from api.task_manager import TaskStatus
        directories = []
        for _ in range(5):
            ident = self.manager.create_task()
            task = self.manager.get_task(ident)
            directories.append(task._cache.directory)
            task.update(status=TaskStatus.COMPLETED, result=[])
        self.manager.clean_old_tasks(max_completed=2)
        self.assertEqual(len(self.manager._tasks), 2)
        self.assertEqual(sum(os.path.exists(path) for path in directories), 2)
