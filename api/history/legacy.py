"""旧扫描页仍获得完整快照；新历史页走轻量详情和按需 K 线接口。"""
from . import store


def list_all(kind):
    records = []
    page = 1
    while True:
        result = store.list_runs(kind=kind, page=page, page_size=200)
        records.extend(result['histories'])
        if len(records) >= result['total']:
            return records
        page += 1


def get(kind, run_id):
    with store._LOCK:
        payload = store.get_run(run_id)
        if payload is None or payload['kind'] != kind:
            return None
        params = payload['params']
        if kind == 'platform_a':
            payload.update(config=params, parameters=params)
        elif kind == 'platform_u':
            payload['request'] = params
        for hit in payload['results']:
            code = hit.get('code') or hit.get('symbol')
            hit['kline_data'] = store.get_kline(run_id, code) or []
        return payload


def delete(kind, run_id):
    with store._LOCK:
        payload = store.get_run(run_id, with_hits=False)
        if payload is None or payload['kind'] != kind:
            return False
        return store.delete_run(run_id)
