"""
Task Manager module for handling long-running tasks.
Implements a simple in-memory task queue with status tracking.
"""
import uuid
import time
from enum import Enum
from typing import Dict, Any, Optional, List, Callable
import threading
import traceback
import json
import os
from pathlib import Path
from collections.abc import MutableMapping
from .task_results import ResultCache, DiskResults
from .json_utils import sanitize_float_for_json

try:
    from api.json_utils import sanitize_task_result
except ImportError:
    # 如果绝对导入失败，尝试相对导入（本地开发环境）
    from .json_utils import sanitize_task_result


class TaskStatus(Enum):
    """Enum representing the possible states of a task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"  # 用户中途停止，结果保留停止前扫到的部分


class Task:
    """Represents a background task with status tracking."""

    def __init__(self, task_id: str, directory=None):
        self.task_id = task_id
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.progress = 0
        self.message = "任务已创建，等待开始"
        self.created_at = time.time()
        self.updated_at = time.time()
        self.completed_at = None

        # 进度计数：scanned 已分析只数 / total 待分析只数 / found 已发现平台期只数
        self.scanned = 0
        self.total = 0
        self.found = 0
        # 取消请求标志，由扫描循环自己检查（不打断正在执行的数据拉取）
        self.cancel_requested = False
        # 扫描过程中逐步追加的结果，客户端按 cursor 增量拉取
        self._cache = ResultCache(directory)
        self.streamed = DiskResults(self._cache, "streamed")
        self.metadata = {}
        self.history_required = False
        self.history_saved = False
        self.history_error = None

    def update(self, status: Optional[TaskStatus] = None,
               progress: Optional[int] = None,
               message: Optional[str] = None,
               result: Any = None,
               error: Optional[str] = None,
               scanned: Optional[int] = None,
               total: Optional[int] = None,
               found: Optional[int] = None) -> None:
        """Update task status and details."""
        if status:
            self.status = status
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                self.completed_at = time.time()

        if progress is not None:
            self.progress = progress

        if message:
            self.message = message

        if result is not None:
            if isinstance(result, list):
                buffer = DiskResults(self._cache, "result")
                codes=[str(item.get('code') or item.get('symbol')) for item in result]
                cached=set(self.streamed.codes())
                if self.history_required and all(code in cached for code in codes):
                    if self.status == TaskStatus.CANCELLED:
                        codes=list(dict.fromkeys([*codes,*self.streamed.codes()]))
                    buffer.select_from(self.streamed,codes)
                else:
                    if self.status == TaskStatus.CANCELLED:
                        seen=set(codes)
                        # Disk iterator keeps payload decoding bounded.
                        def retained():
                            yield from result
                            for item in self.streamed:
                                code=str(item.get('code') or item.get('symbol'))
                                if code not in seen:
                                    seen.add(code)
                                    yield item
                        buffer.replace(retained())
                    else:buffer.replace(result)
                self.result = buffer
            else:
                self.result = result

        if error is not None:
            self.error = error

        if scanned is not None:
            self.scanned = scanned

        if total is not None:
            self.total = total

        if found is not None:
            self.found = found

        self.updated_at = time.time()
        if status is not None:
            self.checkpoint()

    def append_streamed(self, stocks: List[Any]) -> None:
        """Append newly found stocks so the client can render them before the scan ends."""
        if stocks:
            self.streamed.extend(stocks)
            self.updated_at = time.time()

    def to_dict(self, since: int = 0, compact: bool = False) -> Dict[str, Any]:
        """Convert task to dictionary for API responses.

        Args:
            since: 客户端已收到的结果条数，只返回这个位置之后的新结果
        """
        if compact:
            batch = self.streamed.page(since, 100, compact=True, task_id=self.task_id)
            cursor = since + len(batch)
        else:
            batch = sanitize_task_result(self.streamed[since:])
            cursor = len(self.streamed)
        # Sanitize result to handle NaN and Infinity values
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result": None if compact else (sanitize_task_result(self.result) if isinstance(self.result, (list, DiskResults)) else self.result),
            "new_results": batch,
            "cursor": cursor,
            "has_more": cursor < len(self.streamed),
            "result_count": len(self.result) if isinstance(self.result, (list, DiskResults)) else 0,
            "history_id": self.task_id if self.history_saved else None,
            "history_error": self.history_error,
            "history_pending": self.history_required and not self.history_saved and not self.history_error
                               and self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED),
            "scanned": self.scanned,
            "total": self.total,
            "found": self.found,
            "cancel_requested": self.cancel_requested,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at
        }

    def checkpoint(self):
        if not self.history_required:
            return
        data={key:getattr(self,key) for key in ('task_id','message','error','progress','scanned','total','found',
              'cancel_requested','created_at','updated_at','completed_at','metadata','history_saved','history_error')}
        data.update(status=self.status.value, result_present=self.result is not None,
                    result_bucket=self.result.bucket if isinstance(self.result, DiskResults) else None)
        path=Path(self._cache.directory)/'task.json'
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(sanitize_float_for_json(data),ensure_ascii=False,allow_nan=False))
        os.replace(temporary,path)

    def result_page(self, offset=0, limit=100):
        buffer = self.result if isinstance(self.result, DiskResults) else self.streamed
        rows = buffer.page(offset, limit, compact=True, task_id=self.task_id)
        return {"results": rows, "total": len(buffer), "next_offset": offset + len(rows) if offset + len(rows) < len(buffer) else None}

    def kline(self, code):
        return self._cache.kline(code)

    def close(self):
        self._cache.close()


class TaskExtras(MutableMapping):
    """A route-scoped projection; task lifetime owns metadata, no second dictionary."""
    def __init__(self, owner): self.owner = owner
    def __getitem__(self,key):
        task=task_manager.get_task(key)
        if task is None or self.owner not in task.metadata: raise KeyError(key)
        return task.metadata[self.owner]
    def __setitem__(self,key,value):
        task=task_manager.get_task(key)
        if task is None:raise KeyError(key)
        task.metadata[self.owner]=value
        task.history_required=True
        task.checkpoint()
    def __delitem__(self,key):
        task=task_manager.get_task(key)
        if task is None:raise KeyError(key)
        del task.metadata[self.owner]
    def __iter__(self):
        with task_manager._lock:
            keys=[key for key,task in task_manager._tasks.items() if self.owner in task.metadata]
        return iter(keys)
    def __len__(self):return sum(1 for _ in self)


class TaskManager:
    """Manages background tasks and their statuses."""
    _instance = None
    _tasks: Dict[str, Task] = {}
    _lock = threading.RLock()

    def __new__(cls):
        """Singleton pattern to ensure only one TaskManager exists."""
        if cls._instance is None:
            cls._instance = super(TaskManager, cls).__new__(cls)
        return cls._instance

    def create_task(self) -> str:
        """Create a new task and return its ID."""
        self.clean_old_tasks()
        task_id = str(uuid.uuid4())
        with self._lock:
            active=sum(task.status in (TaskStatus.PENDING, TaskStatus.RUNNING) for task in self._tasks.values())
            unsaved=sum(task.history_required and not task.history_saved and task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED) for task in self._tasks.values())
            if active >= 8 or unsaved >= 8:
                from fastapi import HTTPException
                raise HTTPException(429, "任务数量达到上限，请等待运行结束或重试保存失败的历史")
            self._tasks[task_id] = Task(task_id)
        return task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by its ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def payload(self, task_id, since=0, compact=False):
        with self._lock:
            task=self._tasks.get(task_id)
            return task.to_dict(since=since, compact=compact) if task else None

    def update_task(self, task_id: str, **kwargs) -> None:
        """Update a task's status and details."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.update(**kwargs)

    def append_streamed(self, task_id: str, stocks: List[Any]) -> None:
        """Append newly found stocks to a task's streamed results."""
        with self._lock:
            task = self._tasks.get(task_id)
            # A scanner may race with the cancel endpoint between its last
            # check and this callback. The task lock makes the stop boundary
            # authoritative and prevents post-cancel streamed findings.
            if task and not task.cancel_requested:
                task.append_streamed(stocks)
                if len(stocks) == 1:
                    return {key:value for key,value in stocks[0].items() if key != "kline_data"}

    def request_cancel(self, task_id: str) -> bool:
        """Ask a running task to stop. Returns False if the task is unknown or already finished."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False
            task.cancel_requested = True
            task.updated_at = time.time()
            return True

    def is_cancel_requested(self, task_id: str) -> bool:
        """Whether a stop has been requested for this task."""
        with self._lock:
            task = self._tasks.get(task_id)
            return bool(task and task.cancel_requested)

    def run_task_in_background(self, task_id: str, func: Callable, *args, **kwargs) -> None:
        """Run a function in a background thread and track its status."""
        def wrapper():
            task = self.get_task(task_id)
            if not task:
                return

            self.update_task(task_id, status=TaskStatus.RUNNING,
                             message="任务已开始")

            try:
                result = func(*args, **kwargs)
                self.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    result=result,
                    progress=100,
                    message="任务已完成"
                )
            except Exception as e:
                error_msg = f"任务失败：{str(e)}"
                error_traceback = traceback.format_exc()
                self.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    error=f"{error_msg}\n{error_traceback}",
                    message=error_msg
                )

        # Start the background thread
        thread = threading.Thread(target=wrapper)
        thread.daemon = True  # Allow the thread to be terminated when the main process exits
        thread.start()

    def finish_results(self, task_id, items):
        with self._lock:
            task=self._tasks.get(task_id)
            if task:
                codes=[str(item.get('code') or item.get('symbol')) for item in items]
                final=DiskResults(task._cache, 'result')
                final.select_from(task.streamed, codes)
                task.result=final

    def mark_persisted(self, task_id):
        with self._lock:
            task=self._tasks.get(task_id)
            if task:
                task.history_saved=True
                task.history_error=None
                task.checkpoint()

    def recover(self):
        from .task_results import ROOT
        from .history import store
        for path in Path(ROOT).glob('task-*/task.json'):
            try:
                data=json.loads(path.read_text())
                ident=data['task_id']
                if ident in self._tasks:continue
                task=Task(ident, str(path.parent))
                for key in ('message','error','progress','scanned','total','found','cancel_requested','created_at',
                            'updated_at','completed_at','metadata','history_saved','history_error'):
                    if key in data:setattr(task,key,data[key])
                task.status=TaskStatus(data['status'])
                task.history_required=True
                if data.get('result_present'):task.result=DiskResults(task._cache,data.get('result_bucket') or 'result')
                if task.status in (TaskStatus.PENDING,TaskStatus.RUNNING):
                    task.status=TaskStatus.FAILED
                    task.message='服务重启，扫描已中断；已找到的结果可查看（中断前扫描进度未完整恢复）'
                    task.found=len(task.streamed)
                    task.completed_at=time.time()
                    task.result=task.streamed
                if not task.history_saved:
                    task.history_saved=store.get_run(ident, with_hits=False) is not None
                self._tasks[ident]=task
                task.checkpoint()
            except Exception as error:
                # Preserve the files for recovery; never delete an unreadable journal.
                print(f'Task recovery failed for {path.name}: {error}')
        self.clean_old_tasks()

    def save_pending_history(self, task_id):
        from .history import store
        task=self.get_task(task_id)
        if task is None:raise ValueError('任务不存在')
        if task.status in (TaskStatus.PENDING,TaskStatus.RUNNING):raise ValueError('任务尚未结束')
        if task.history_saved:return
        if not task.metadata:raise ValueError('缺少扫描参数，无法恢复历史')
        kind,meta=next(iter(task.metadata.items()))
        params=meta.get('params',meta)
        snapshot={key:getattr(task,key) for key in ('task_id','message','error','created_at','completed_at','scanned','total','found')}
        snapshot.update(status=task.status.value, params=params, config=params, request=params,
            frequency=meta.get('frequency',params.get('frequency','1h' if kind.endswith('_u') else '60')),
            scan_date=meta.get('scan_date'),rules=meta.get('rules',[]),stats=meta.get('stats'),
            results=task.result if task.result is not None else task.streamed)
        try:store.save_run(kind,task_id,snapshot)
        except Exception as error:
            task.history_error=str(error)
            task.checkpoint()
            raise

    def clean_old_tasks(self, max_age_seconds=3600, max_completed=8):
        now=time.time()
        with self._lock:
            completed=sorted((t for t in self._tasks.values()
                if t.status in (TaskStatus.COMPLETED,TaskStatus.FAILED,TaskStatus.CANCELLED)
                and (not t.history_required or t.history_saved)), key=lambda t:t.completed_at or 0)
            excess=max(0,len(completed)-max_completed)
            for index,task in enumerate(completed):
                if index < excess or now-(task.completed_at or now)>max_age_seconds:
                    self._tasks.pop(task.task_id,None)
                    task.close()

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks as dictionaries."""
        with self._lock:
            return [task.to_dict() for task in self._tasks.values()]


# Create a singleton instance
task_manager = TaskManager()
