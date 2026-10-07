"""Disk-backed scan payloads. Only one result page/K-line is decoded at a time."""
import json
import os
import sqlite3
import tempfile
import shutil
from contextlib import contextmanager
from collections.abc import Sequence
from .json_utils import sanitize_float_for_json

ROOT = os.environ.get('HENGPAN_TASK_CACHE_ROOT') or os.path.join(os.path.dirname(__file__), 'data', 'task-cache')

class ResultCache:
    def __init__(self, directory=None):
        os.makedirs(ROOT, exist_ok=True)
        self.directory = directory or tempfile.mkdtemp(prefix='task-', dir=ROOT)
        self.path = os.path.join(self.directory, 'results.db')
        with self.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS results (bucket TEXT, seq INTEGER, code TEXT, detail TEXT, kline TEXT, PRIMARY KEY(bucket,seq))')
            conn.execute('CREATE INDEX IF NOT EXISTS result_code ON results(code,bucket)')
    @contextmanager
    def connect(self):
        conn=sqlite3.connect(self.path, timeout=30)
        try:
            with conn:yield conn
        finally:conn.close()
    def close(self):
        shutil.rmtree(self.directory, ignore_errors=True)
    def kline(self, code):
        with self.connect() as conn:
            row = conn.execute("SELECT kline FROM results WHERE code=? ORDER BY bucket ASC LIMIT 1",(code,)).fetchone()
        return json.loads(row[0]) if row else None

class DiskResults(Sequence):
    def __init__(self, cache, bucket):
        self.cache, self.bucket = cache, bucket
    def select_from(self, source, codes):
        with self.cache.connect() as conn:
            conn.execute('DELETE FROM results WHERE bucket=?',(self.bucket,))
            for seq,code in enumerate(codes):
                cursor=conn.execute('INSERT INTO results SELECT ?,?,code,detail,kline FROM results WHERE bucket=? AND code=? ORDER BY seq LIMIT 1', (self.bucket,seq,source.bucket,str(code)))
                if cursor.rowcount != 1:raise ValueError(f'结果缓存缺失：{code}')

    def codes(self):
        with self.cache.connect() as conn:
            return [row[0] for row in conn.execute('SELECT code FROM results WHERE bucket=? ORDER BY seq',(self.bucket,))]

    def __len__(self):
        with self.cache.connect() as conn:
            return conn.execute('SELECT count(*) FROM results WHERE bucket=?',(self.bucket,)).fetchone()[0]
    def replace(self, items):
        self._write(items, replace=True)
    def extend(self, items):
        self._write(items, replace=False)
    def _write(self, items, replace):
        with self.cache.connect() as conn:
            if replace: conn.execute('DELETE FROM results WHERE bucket=?',(self.bucket,))
            seq=conn.execute('SELECT count(*) FROM results WHERE bucket=?',(self.bucket,)).fetchone()[0]
            for item in items:
                item=sanitize_float_for_json(item)
                detail={k:v for k,v in item.items() if k!='kline_data'}
                rows=item.get('kline_data') or []
                if len(rows) >= 2:
                    previous=rows[-2].get('close')
                    current=rows[-1].get('close')
                    if previous and current is not None:
                        detail['last_change_ratio']=current/previous-1
                code=str(item.get('code') or item.get('symbol') or seq)
                conn.execute('INSERT INTO results VALUES (?,?,?,?,?)',(self.bucket,seq,code,json.dumps(detail,ensure_ascii=False,allow_nan=False),json.dumps(rows,ensure_ascii=False,allow_nan=False)))
                seq+=1
    def page(self, offset=0, limit=100, compact=False, task_id=None):
        select='code,detail' if compact else 'code,detail,kline'
        with self.cache.connect() as conn:
            rows=conn.execute(f'SELECT {select} FROM results WHERE bucket=? ORDER BY seq LIMIT ? OFFSET ?', (self.bucket,limit,offset)).fetchall()
        result=[]
        for row in rows:
            detail=json.loads(row[1])
            if 'last_change' in detail and 'last_change_ratio' not in detail:
                detail['last_change_ratio']=detail.pop('last_change')/100
            detail['kline_data']=[] if compact else json.loads(row[2])
            if compact and task_id:
                from urllib.parse import quote
                detail['kline_url']=f'/api/tasks/{quote(task_id,safe="")}/kline/{quote(row[0],safe="")}'
            result.append(detail)
        return result
    def __getitem__(self,index):
        if isinstance(index,slice):
            start,stop,step=index.indices(len(self))
            return self.page(start,max(0,stop-start))[::step]
        if index<0:index+=len(self)
        rows=self.page(index,1)
        if not rows:raise IndexError(index)
        return rows[0]
    def __iter__(self):
        offset=0
        while True:
            rows=self.page(offset,32)
            if not rows:return
            yield from rows
            offset+=len(rows)
