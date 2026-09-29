"""统一历史和旧接口间的兼容回归，所有数据均写入临时目录。"""
import os
import tempfile
import unittest
from unittest.mock import patch

from api import scan_history
from api.crypto import platform_history, hengpan_history
from api.hengpan import history
from api.history import db, store
from api.history.adapters import params_hash
from api.history.tests.test_store import _hengpan_a_snapshot, _platform_a_snapshot


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.multiple(db, DB_PATH=os.path.join(self.temp.name, 'history.db'),
                                 KLINE_DIR=os.path.join(self.temp.name, 'klines'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_legacy_detail_keeps_klines_and_parameter_aliases(self):
        snapshot = _platform_a_snapshot()
        scan_history.save_scan_history('p', snapshot)
        result = scan_history.get_scan_history('p')
        self.assertEqual(result.get('config'), snapshot['config'])
        self.assertEqual(result.get('parameters'), snapshot['parameters'])
        self.assertEqual(result['results'][0]['kline_data'], snapshot['results'][0]['kline_data'])
        self.assertEqual(store.get_run('p')['results'][0]['kline_data'], [])
        platform_history.save('u', {'request': {'windows': [40]}, 'results': []})
        self.assertEqual(platform_history.get('u').get('request'), {'windows': [40]})

    def test_legacy_kind_cannot_read_or_delete_other_market(self):
        history.save_history('a', _hengpan_a_snapshot())
        self.assertIsNone(hengpan_history.get_history('a'))
        self.assertFalse(hengpan_history.delete_history('a'))
        self.assertIsNotNone(history.get_history('a'))

    def test_every_effective_parameter_changes_fingerprint(self):
        self.assertNotEqual(params_hash('platform_a', {'box_threshold': .02}),
                            params_hash('platform_a', {'box_threshold': .03}))
        self.assertNotEqual(params_hash('hengpan_u', {'symbols': ['BTCUSDT']}),
                            params_hash('hengpan_u', {'symbols': ['ETHUSDT']}))

    def test_invalid_path_segments_are_rejected(self):
        for run_id in ('..', '.', '', '../data', '/tmp/test'):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                store.save_run('hengpan_a', run_id, {'results': []})

    def test_failed_replacement_keeps_old_record_and_chart(self):
        original = _hengpan_a_snapshot()
        history.save_history('a', original)
        with patch.object(store, '_write_klines', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                history.save_history('a', _hengpan_a_snapshot(codes=('sz.000001',)))
        self.assertEqual(store.get_kline('a', 'sh.600519'), original['results'][0]['kline_data'])
        self.assertEqual(store.get_run('a')['results'][0]['code'], 'sh.600519')

    def test_aggregation_merges_symbols_and_does_not_count_repeat_scan_as_new_rule(self):
        first = _hengpan_a_snapshot()
        history.save_history('a1', first)
        history.save_history('a2', first)
        grouped = store.list_symbols(market='a', intraday_only=True)
        self.assertEqual(grouped['total'], 1)
        self.assertEqual(grouped['symbols'][0]['code'], 'sh.600519')
        self.assertEqual(grouped['symbols'][0]['run_count'], 2)
        self.assertEqual(grouped['symbols'][0]['rule_count'], 2)

    def test_legacy_lists_do_not_truncate_at_200(self):
        for index in range(205):
            history.save_history(f'a{index}', {'frequency': '60', 'results': []})
        self.assertEqual(len(history.list_histories()), 205)


if __name__ == '__main__':
    unittest.main()
