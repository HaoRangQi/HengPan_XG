"""Actual ASGI contract checks for all four compact scan status routes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import asyncio
import json
from urllib.parse import urlsplit, unquote
from types import SimpleNamespace
from api.index import app
from api.history import db
from api.task_manager import TaskExtras, TaskStatus, task_manager

ROUTES = {
    'platform_a': '/api/scan/status/',
    'platform_u': '/api/crypto/platform/scan/status/',
    'hengpan_a': '/api/hengpan/scan/status/',
    'hengpan_u': '/api/crypto/hengpan/scan/status/',
}


class AsgiClient:
    async def get(self, url):
        parsed = urlsplit(url)
        messages = []
        requested = False
        async def receive():
            nonlocal requested
            if not requested:
                requested = True
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            await asyncio.Event().wait()
        async def send(message):
            messages.append(message)
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
                 'http_version': '1.1', 'method': 'GET', 'scheme': 'http',
                 'path': unquote(parsed.path), 'raw_path': parsed.path.encode(),
                 'query_string': parsed.query.encode(), 'root_path': '',
                 'headers': [], 'client': ('127.0.0.1', 1234), 'server': ('test', 80)}
        await asyncio.wait_for(app(scope, receive, send), 10)
        status = next(message['status'] for message in messages if message['type'] == 'http.response.start')
        text = b''.join(message.get('body', b'') for message in messages if message['type'] == 'http.response.body').decode()
        return SimpleNamespace(status_code=status, text=text, json=lambda: json.loads(text))


class TaskAsgiReviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch('api.task_results.ROOT', str(root / 'cache')),
                        patch.object(task_manager, '_tasks', {}),
                        patch.object(db, 'DB_PATH', str(root / 'history.db')),
                        patch.object(db, 'KLINE_DIR', str(root / 'klines'))]
        for item in self.patches:
            item.start()
        self.client = AsgiClient()

    async def asyncTearDown(self):
        for task in list(task_manager._tasks.values()):
            task.close()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def task(self, kind, final=True):
        ident = task_manager.create_task()
        params = {'frequency': '1h' if kind.endswith('_u') else '60', 'windows': [20]}
        TaskExtras(kind)[ident] = {'params': params, 'rules': [], 'scan_date': '2026-10-01',
                                  'frequency': params['frequency'], 'stats': {}}
        task_manager.append_streamed(ident, [{'code': 'A', 'symbol': 'A', 'name': 'demo',
                                             'is_st': None, 'kline_data': [{'close': 10.}]}])
        task_manager.finish_results(ident, [{'code': 'A'}] if final else [])
        task_manager.update_task(ident, status=TaskStatus.COMPLETED)
        return ident

    async def test_all_four_compact_final_pages_and_klines(self):
        for kind, route in ROUTES.items():
            with self.subTest(kind=kind):
                ident = self.task(kind)
                status = await self.client.get(route + ident + '?compact=true')
                self.assertEqual(status.status_code, 200, status.text)
                payload = status.json()
                self.assertIsNone(payload['result'])
                self.assertEqual(payload['new_results'][0]['kline_data'], [])
                self.assertEqual(payload['result_count'], 1)
                page = (await self.client.get(f'/api/tasks/{ident}/results?offset=0&limit=100')).json()
                self.assertEqual(page['total'], 1)
                chart = await self.client.get(page['results'][0]['kline_url'])
                self.assertEqual(chart.json()['kline_data'], [{'close': 10.}])

    async def test_all_four_terminal_zero_and_namespace_guards(self):
        for kind, route in ROUTES.items():
            with self.subTest(kind=kind):
                ident = self.task(kind, final=False)
                status = await self.client.get(route + ident + '?compact=true')
                self.assertEqual(status.json()['result_count'], 0)
                page = (await self.client.get(f'/api/tasks/{ident}/results')).json()
                self.assertEqual(page['results'], [])
                self.assertEqual(page['total'], 0)
                for other_kind, other_route in ROUTES.items():
                    if other_kind != kind:
                        self.assertEqual((await self.client.get(other_route + ident + '?compact=true')).status_code, 404)

    async def test_all_four_history_fallback_preserves_klines_after_cache_expiry(self):
        for kind in ROUTES:
            with self.subTest(kind=kind):
                ident = self.task(kind)
                task_manager.save_pending_history(ident)
                task_manager.clean_old_tasks(max_age_seconds=0, max_completed=0)
                response = await self.client.get(f'/api/tasks/{ident}/results')
                self.assertEqual(response.status_code, 200, response.text)
                page = response.json()
                self.assertEqual(page['total'], 1)
                chart = await self.client.get(page['results'][0]['kline_url'])
                self.assertEqual(chart.json()['kline_data'], [{'close': 10.}])
