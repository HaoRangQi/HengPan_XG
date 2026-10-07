import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from api import case_manager


class CaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.legacy = self.root / 'cases'
        self.legacy.mkdir()
        self.index = self.legacy / 'index.json'
        self.index.write_text('{"cases": []}', encoding='utf-8')
        for name, value in [('CASE_DIR', str(self.legacy)), ('INDEX_FILE', str(self.index)),
                            ('CASE_DB', str(self.root / 'cases.db'))]:
            p = patch.object(case_manager, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)

    def payload(self, **extra):
        return dict(title='Example', stockCode='sh.600000', stockName='Example',
                    description='Saved description', analysis={'score': 1},
                    kline_data={'data': [{'close': 1}]}, **extra)

    def test_same_second_saves_are_independent(self):
        with patch.object(case_manager, 'datetime') as clock:
            clock.now.return_value = datetime(2026, 10, 6)
            first = case_manager.create_case(self.payload())
            second = case_manager.create_case(self.payload())
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(len(case_manager.get_cases()), 2)

    def test_client_id_rejected_without_writing_outside_storage(self):
        for unsafe in ['../outside', str(self.root / 'absolute-untrusted-case'), 'client-id']:
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                case_manager.create_case(self.payload(id=unsafe))
        self.assertEqual(case_manager.get_cases(), [])
        self.assertFalse((self.root / 'outside').exists())

    def legacy_case(self, case_id='case_123'):
        data = self.payload()
        data.update(id=case_id, createdAt='2020', updatedAt='2020', tags=[])
        directory = self.legacy / case_id
        directory.mkdir()
        (directory / 'description.md').write_text(data.pop('description'))
        for field in ['analysis', 'kline_data']:
            (directory / (field + '.json')).write_text(json.dumps(data.pop(field)))
        self.index.write_text(json.dumps({'cases': [data]}))
        return data

    def test_duplicate_legacy_ids_are_reported(self):
        meta = self.legacy_case()
        self.index.write_text(json.dumps({'cases': [meta, meta]}))
        with self.assertRaisesRegex(Exception, 'duplicate|重复'):
            case_manager.get_cases()

    def test_unsafe_legacy_ids_are_reported(self):
        meta = self.legacy_case()
        meta['id'] = '../outside'
        self.index.write_text(json.dumps({'cases': [meta]}))
        with self.assertRaisesRegex(Exception, 'unsafe|非法'):
            case_manager.get_cases()

    def test_corrupt_legacy_content_is_reported(self):
        self.legacy_case()
        (self.legacy / 'case_123' / 'analysis.json').write_text('{bad')
        with self.assertRaisesRegex(Exception, 'analysis.json'):
            case_manager.get_cases()

    def test_missing_optional_legacy_content_is_migrated_with_warning(self):
        self.legacy_case()
        (self.legacy / 'case_123' / 'kline_data.json').unlink()
        case = case_manager.get_case('case_123')
        self.assertNotIn('kline_data', case)
        status, result = self.call_api('GET', '/api/cases')
        self.assertEqual(status, 200)
        self.assertTrue(any('kline_data.json' in warning for warning in result['migration']['warnings']))

    def test_successful_migration_backed_up_once_and_no_dual_write(self):
        self.legacy_case()
        before = self.index.read_bytes()
        original = case_manager.get_case('case_123')
        self.assertEqual(original['description'], 'Saved description')
        self.assertEqual(len(list(self.root.glob('cases-legacy-backup-*'))), 1)
        updated = case_manager.update_case('case_123', {'description': 'Changed'})
        self.assertEqual(updated['description'], 'Changed')
        self.assertEqual(case_manager.get_case('case_123')['analysis'], {'score': 1})
        self.assertTrue(case_manager.delete_case('case_123'))
        self.assertIsNone(case_manager.get_case('case_123'))
        self.assertEqual(case_manager.get_cases(), [])
        self.assertEqual(self.index.read_bytes(), before)
        self.assertEqual((self.legacy / 'case_123' / 'description.md').read_text(), 'Saved description')
        self.assertEqual(len(list(self.root.glob('cases-legacy-backup-*'))), 1)

    def test_failed_migration_retries_after_repair_without_partial_import(self):
        import sqlite3
        self.legacy_case()
        path = self.legacy / 'case_123' / 'analysis.json'
        path.write_text('bad')
        with self.assertRaises(Exception):
            case_manager.get_cases()
        with sqlite3.connect(case_manager.CASE_DB) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if ('cases',) in tables:
                self.assertEqual(conn.execute('SELECT count(*) FROM cases').fetchone()[0], 0)
        path.write_text('{"score":2}')
        self.assertEqual(case_manager.get_case('case_123')['analysis'], {'score': 2})
        self.assertEqual(len(case_manager.get_cases()), 1)

    def test_symlink_and_orphan_migration_blocked(self):
        self.legacy_case()
        outside = self.root / 'outside.json'
        outside.write_text('{"private":true}')
        path = self.legacy / 'case_123' / 'analysis.json'
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(Exception, 'symlink'):
            case_manager.get_cases()
        path.unlink()
        path.write_text('{}')
        (self.legacy / 'unindexed').mkdir()
        with self.assertRaisesRegex(Exception, 'unindexed'):
            case_manager.get_cases()

    def test_create_and_update_serialization_failure_is_atomic(self):
        original = case_manager.create_case(self.payload())
        with self.assertRaises((ValueError, TypeError)):
            case_manager.create_case(self.payload(bad='ignored') | {'analysis': {'bad': object()}})
        with self.assertRaises((ValueError, TypeError)):
            case_manager.update_case(original['id'], {'title': 'Changed', 'analysis': {'bad': object()}})
        self.assertEqual(case_manager.get_case(original['id']), original)
        self.assertEqual(len(case_manager.get_cases()), 1)

    def test_concurrent_saves_and_updates_preserve_all_fields(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as executor:
            cases = list(executor.map(lambda _: case_manager.create_case(self.payload()), range(20)))
            list(executor.map(lambda item: case_manager.update_case(cases[0]['id'], item),
                              [{'title': 'Changed'}, {'description': 'Changed'}]))
        self.assertEqual(len({case['id'] for case in cases}), 20)
        self.assertEqual(len(case_manager.get_cases()), 20)
        updated = case_manager.get_case(cases[0]['id'])
        self.assertEqual(updated['title'], 'Changed')
        self.assertEqual(updated['description'], 'Changed')

    def call_api(self, method, path, body=None):
        import asyncio
        from fastapi import FastAPI
        from api.case_api import router
        app = FastAPI()
        app.include_router(router, prefix='/api')
        async def request():
            messages = []
            async def receive():
                return {'type': 'http.request', 'body': json.dumps(body or {}).encode(), 'more_body': False}
            async def send(message):
                messages.append(message)
            try:
                await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                           'method': method, 'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                           'query_string': b'', 'root_path': '',
                           'headers': [(b'content-type', b'application/json')],
                           'client': ('127.0.0.1', 12345), 'server': ('test', 80)}, receive, send)
            except Exception:
                if not messages:
                    raise
            status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
            data = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
            try:
                return status, json.loads(data)
            except ValueError:
                return status, data.decode()
        return asyncio.run(request())

    def test_api_crud_demo_export_and_error_contract(self):
        self.assertEqual(self.call_api('POST', '/api/cases', self.payload(id='../outside'))[0], 400)
        status, created = self.call_api('POST', '/api/cases', self.payload())
        self.assertEqual(status, 200)
        url = '/api/cases/' + created['id']
        self.assertEqual(self.call_api('PUT', url, {'title': 'Changed'})[1]['title'], 'Changed')
        self.assertEqual(self.call_api('PUT', url, {'id': '../outside'})[0], 400)
        self.assertEqual(self.call_api('GET', url)[1]['description'], 'Saved description')
        self.assertEqual(self.call_api('POST', '/api/cases/create-anjishi')[0], 200)
        status, exported = self.call_api('POST', '/api/cases/export', {
            'stockData': {'code': 'x', 'name': 'Example'}, 'analysisResult': {}, 'klineData': [{'close': 1}]})
        self.assertEqual(status, 200)
        self.assertTrue(exported['success'])
        self.assertEqual(len(self.call_api('GET', '/api/cases')[1]['cases']), 3)
        self.assertEqual(self.call_api('DELETE', url)[1], {'success': True})
        self.assertEqual(self.call_api('GET', url)[0], 404)

    def test_api_migration_errors_explicit(self):
        self.index.write_text('{bad')
        status, result = self.call_api('GET', '/api/cases')
        self.assertEqual(status, 503)
        self.assertIn('index.json', result['detail'])

    def test_repeated_migration_errors_do_not_multiply_backups(self):
        self.legacy_case()
        (self.legacy / 'case_123' / 'analysis.json').write_text('bad')
        for _ in range(3):
            with self.assertRaises(Exception):
                case_manager.get_cases()
        self.assertEqual(len(list(self.root.glob('cases-legacy-backup-*'))), 1)

    def test_minimal_legacy_case_without_optional_files_is_valid(self):
        self.legacy_case()
        for path in (self.legacy / 'case_123').iterdir():
            path.unlink()
        case = case_manager.get_case('case_123')
        self.assertEqual(case['title'], 'Example')
        self.assertNotIn('description', case)
        self.assertNotIn('analysis', case)
        self.assertNotIn('kline_data', case)
        self.assertEqual(len(self.call_api('GET', '/api/cases')[1]['migration']['warnings']), 3)

    def test_missing_legacy_case_directory_remains_error(self):
        self.legacy_case()
        import shutil
        shutil.rmtree(self.legacy / 'case_123')
        with self.assertRaisesRegex(Exception, 'missing directory'):
            case_manager.get_cases()
