"""ST status is a date-specific source fact, never inferred from a current name."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pandas as pd
from api.store import db, sync
from api.store.reader import load_kline_60m
from api.store.tests.test_reader import ReaderTestCase


class DailyStatusTests(ReaderTestCase):
    def setUp(self):
        super().setUp()
        db.upsert(self.conn, 'stock_basic', ('code', 'code_name', 'type', 'status', 'board'),
                  [('sh.600000', 'normal name', '1', '1', 'sh_main')])
        for date in ('2026-09-23', '2026-09-24', '2026-09-25'):
            self.seed_bar('sh_main', date, date.replace('-', '') + '150000000', 'sh.600000',
                          ('10', '11', '9', '10'))
        self.conn.commit()

    def run_sync(self, fetch, **kwargs):
        with patch('api.store.sync.ProcessPoolExecutor', ThreadPoolExecutor), \
             patch('api.store.sync._init_worker'), \
             patch('api.store.sync.fetch_daily_status_rows', side_effect=fetch) as query:
            stats = sync.sync_daily_status(self.conn, boards=['sh_main'], end_date='2026-09-25', **kwargs)
        return stats, query

    def test_fetch_preserves_true_false_and_ignores_invalid_status(self):
        frame = pd.DataFrame({'date': ['2026-09-23', '2026-09-24', '2026-09-25'],
                              'isST': ['1', '0', '']})
        with patch('api.store.sync.query_kline', return_value=frame) as query:
            rows = sync.fetch_daily_status_rows('sh.600000', '2026-09-23', '2026-09-25')
        self.assertEqual(rows, [('sh.600000', '2026-09-23', '1'), ('sh.600000', '2026-09-24', '0')])
        self.assertEqual(query.call_args.kwargs['frequency'], 'd')

    def test_sync_and_reader_exact_date_without_forward_fill(self):
        stats, query = self.run_sync(lambda *args: [('sh.600000', '2026-09-23', '1'),
                                                   ('sh.600000', '2026-09-25', '0')])
        self.assertEqual(stats['requests'], 1)
        self.assertEqual(stats['rows'], 2)
        self.assertEqual(stats['unknown'], 1)
        values = load_kline_60m(self.conn, ['sh_main'], adjust='raw')['isST'].tolist()
        self.assertEqual(values, ['1', None, '0'])
        self.assertEqual(query.call_args.args[:3], ('sh.600000', '2026-09-23', '2026-09-25'))

    def test_failure_leaves_unknown_and_counts_request(self):
        stats, _ = self.run_sync(OSError('daily unavailable'))
        self.assertEqual(stats['requests'], 1)
        self.assertEqual(stats['failed'], 1)
        self.assertEqual(stats['unknown'], 3)
        self.assertTrue(load_kline_60m(self.conn, ['sh_main'], adjust='raw')['isST'].isna().all())

    def test_empty_response_is_unknown_not_normal(self):
        stats, _ = self.run_sync(lambda *args: [])
        self.assertEqual(stats['empty'], 1)
        self.assertEqual(stats['unknown'], 3)

    def test_complete_status_makes_no_request(self):
        self.run_sync(lambda *args: [('sh.600000', day, '0') for day in ('2026-09-23', '2026-09-24', '2026-09-25')])
        stats, query = self.run_sync(AssertionError('already known'))
        self.assertEqual(stats['requests'], 0)
        self.assertEqual(stats['unknown'], 0)
        query.assert_not_called()

    def test_cancelled_before_start_makes_no_request(self):
        stats, query = self.run_sync(AssertionError('cancelled'), should_cancel=lambda: True)
        self.assertTrue(stats['cancelled'])
        query.assert_not_called()

    def test_legacy_database_without_status_table_remains_unknown(self):
        self.conn.execute('DROP TABLE IF EXISTS stock_daily_status')
        self.assertTrue(load_kline_60m(self.conn, ['sh_main'], adjust='raw')['isST'].isna().all())

    def test_explicit_full_sync_includes_status_backfill_request_cost(self):
        kline = {"rows": 0, "requests": 0, "failed": 0, "cancelled": False,
                 "start_date": None, "up_to_date": 1, "probe": 0}
        with patch('api.store.sync._calendar_is_stale', return_value=False), \
             patch('api.store.sync._metadata_is_stale', return_value=False), \
             patch('api.store.sync.resolve_end_date', return_value='2026-09-25'), \
             patch('api.store.sync.sync_initial_adjust_factors', return_value={"requests": 0, "failed": 0, "cancelled": False}), \
             patch('api.store.sync.sync_adjust_factor_by_day', return_value=(0, 0)), \
             patch('api.store.sync.sync_kline', return_value=kline), \
             patch('api.store.sync.ProcessPoolExecutor', ThreadPoolExecutor), \
             patch('api.store.sync._init_worker'), \
             patch('api.store.sync.fetch_daily_status_rows', return_value=[('sh.600000', '2026-09-25', '1')]):
            stats = sync.sync_all(self.conn, boards=['sh_main'], codes=['sh.600000'])
        self.assertEqual(stats['requests'], 1)
        self.assertEqual(stats['status_requests'], 1)
        self.assertEqual(stats['status_rows'], 1)
        self.assertEqual(stats['status_unknown'], 2)
        self.assertIn('状态未知', stats['message'])
