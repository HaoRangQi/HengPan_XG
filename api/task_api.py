"""Lightweight task result pages; persistent history remains available after cache expiry."""
from fastapi import APIRouter, HTTPException, Query
from .task_manager import task_manager
from .history import store

router=APIRouter()

@router.get('/tasks/{task_id}/results')
def results(task_id: str, offset: int=Query(0,ge=0),limit: int=Query(100,ge=1,le=100)):
    with task_manager._lock:
        task=task_manager.get_task(task_id)
        if task:return task.result_page(offset,limit)
    page=store.result_page(task_id, offset=offset, limit=limit)
    if page is None:raise HTTPException(404,'任务与历史记录均不存在')
    from urllib.parse import quote
    for row in page['results']:
        code=row.get('code') or row.get('symbol')
        row['kline_url']=f'/api/history/{quote(task_id, safe="")}/kline/{quote(str(code), safe="")}'
    return page

@router.get('/tasks/{task_id}/kline/{code}')
def kline(task_id: str,code: str):
    with task_manager._lock:
        task=task_manager.get_task(task_id)
        rows=task.kline(code) if task else None
    if rows is None:
        try:rows=store.get_kline(task_id,code)
        except ValueError:raise HTTPException(422,'无效标的')
    if rows is None:raise HTTPException(404,'K线快照不存在')
    return {'kline_data':rows}

@router.post('/tasks/{task_id}/history/retry')
def retry_history(task_id: str):
    try:task_manager.save_pending_history(task_id)
    except ValueError as error:raise HTTPException(400,str(error))
    except Exception as error:raise HTTPException(503,f'保存历史失败：{error}')
    return {'history_id':task_id,'saved':True}

@router.get('/tasks/{task_id}/status')
def historical_status(task_id: str):
    payload=task_manager.payload(task_id, compact=True)
    if payload is not None:return payload
    item=store.get_run(task_id,with_hits=False)
    if item is None:raise HTTPException(404,'任务或历史记录不存在')
    return {**item,'task_id':task_id,'status':item['status'],'progress':100,
            'history_id':task_id,'result':None,'new_results':[],'cursor':0,
            'has_more':False,'result_count':item.get('found',0)}

@router.get('/tasks/recoverable')
def recoverable_tasks():
    with task_manager._lock:
        return {'tasks':[
            {'task_id':task.task_id,'message':task.message,'error':task.history_error,
             'kind':next(iter(task.metadata),None),'found':len(task.result if task.result is not None else task.streamed)}
            for task in task_manager._tasks.values()
            if task.history_required and not task.history_saved
            and task.status.value in ('completed','failed','cancelled')
        ]}
