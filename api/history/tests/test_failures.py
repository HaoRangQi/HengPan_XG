"""失败的扫描也要归档，归档失败不能把已完成的扫描改成失败。"""
import asyncio
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks
from api import index
from api.hengpan import router as a
from api.crypto import hengpan_router as u, platform_router as p
from api.task_manager import task_manager


class FailedHistoryTest(unittest.TestCase):
    def test_anchored_failures_are_saved(self):
        for module, request, data_db in ((a, a.HengpanScanRequest(), a.store_db),
                                         (u, u.CryptoHengpanScanRequest(), u.db)):
            with self.subTest(module=module.__name__):
                task_id = task_manager.create_task()
                params = request.model_dump()
                module._extras[task_id] = {'scan_date': '', 'stats': None}
                with patch.object(data_db, 'open_db', side_effect=ConnectionError('offline')), \
                        patch.object(module, 'save_history') as save:
                    module._run_scan(task_id, params, [])
                    self.assertEqual(save.call_count, 1)
                    snapshot = save.call_args.args[1]
                    self.assertEqual(snapshot['status'], 'failed')
                    self.assertIn('offline', snapshot['error'])
                    self.assertEqual(list(snapshot['results']), [])

    def test_platform_crypto_failure_is_saved(self):
        task_id = task_manager.create_task()
        with patch.object(p.db, 'open_db', side_effect=ConnectionError('offline')), \
                patch.object(p, 'save') as save:
            p._run_scan(task_id, p.CryptoPlatformScanRequest().model_dump())
            self.assertEqual(save.call_count, 1)
            self.assertEqual(save.call_args.args[1]['status'], 'failed')
            self.assertIn('offline', save.call_args.args[1]['error'])

    def test_platform_a_failure_is_saved(self):
        async def run():
            tasks = BackgroundTasks()
            with patch.object(index, 'prepare_platform_scan_source', side_effect=ValueError('offline')), \
                    patch.object(index, 'save_scan_history') as save:
                await index.start_scan(index.ScanConfigRequest(data_source='local', frequency='60'), tasks)
                await tasks()
                self.assertEqual(save.call_count, 1)
                self.assertEqual(save.call_args.args[1]['status'], 'failed')
        asyncio.run(run())
