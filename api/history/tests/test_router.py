"""通过 ASGI 请求覆盖路由匹配、校验、CRUD 和按需 K 线，无额外测试依赖。"""
import asyncio
import json
from urllib.parse import urlsplit

from api.index import app
from api.history import store
from api.history.tests.test_integration import IntegrationTest
from api.history.tests.test_store import _hengpan_a_snapshot


async def request(method, url, body=None):
    parts = urlsplit(url)
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {'type': 'http.request', 'body': json.dumps(body or {}).encode(), 'more_body': False}
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)

    await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
               'method': method, 'scheme': 'http', 'path': parts.path,
               'raw_path': parts.path.encode(), 'query_string': parts.query.encode(),
               'root_path': '', 'headers': [(b'content-type', b'application/json')],
               'client': ('127.0.0.1', 12345), 'server': ('testserver', 80)}, receive, send)
    status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
    data = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    return status, json.loads(data)


class RouterTest(IntegrationTest):
    def call(self, method, url, body=None):
        return asyncio.run(request(method, url, body))

    def test_http_crud_and_symbol_view(self):
        store.save_run('hengpan_a', 'a', _hengpan_a_snapshot())
        store.save_run('hengpan_a', 'b', _hengpan_a_snapshot())
        status, result = self.call('GET', '/api/history?view=symbols&market=a')
        self.assertEqual(status, 200)
        self.assertIn('symbols', result)
        self.assertEqual(result['total'], 1)
        self.assertEqual(self.call('GET', '/api/history/overview')[1]['runs'], 2)
        detail = self.call('GET', '/api/history/a')[1]
        self.assertEqual(detail['results'][0]['kline_data'], [])
        chart = self.call('GET', '/api/history/a/kline/sh.600519')[1]
        self.assertTrue(chart['kline_data'])
        edited = self.call('PATCH', '/api/history/a', {'note': '观察', 'pinned': True})[1]
        self.assertEqual(edited['note'], '观察')
        self.assertTrue(edited['pinned'])
        self.assertEqual(self.call('DELETE', '/api/history/b')[0], 200)
        self.assertEqual(self.call('GET', '/api/history/b')[0], 404)

    def test_http_validation(self):
        for query in ('status=nope', 'frequency=nope', 'date_from=2026-02-31',
                      'date_from=2026-09-30&date_to=2026-09-01', 'view=nope'):
            with self.subTest(query=query):
                self.assertEqual(self.call('GET', '/api/history?' + query)[0], 422)
        self.assertEqual(self.call('POST', '/api/history/cleanup', {})[0], 422)
        self.assertEqual(self.call('GET', '/api/history/missing/kline/BTCUSDT')[0], 404)

    def test_cleanup_preview_does_not_delete(self):
        store.save_run('hengpan_a', 'a', _hengpan_a_snapshot())
        store.save_run('hengpan_a', 'b', _hengpan_a_snapshot())
        preview = self.call('POST', '/api/history/cleanup', {'keep_count': 1, 'apply': False})
        self.assertEqual(preview[0], 200)
        self.assertEqual(store.overview()['runs'], 2)
        result = self.call('POST', '/api/history/cleanup', {'keep_count': 1, 'apply': True})[1]
        self.assertEqual(result['deleted'], 1)
        self.assertEqual(store.overview()['runs'], 1)
