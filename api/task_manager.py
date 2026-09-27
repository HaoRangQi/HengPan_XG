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

    def __init__(self, task_id: str):
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
        self.streamed: List[Any] = []

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
            # Keep terminal result compatible with incremental output. The
            # scanner may apply a post-filter after on_found has streamed a
            # stock; never make an already displayed finding disappear.
            if isinstance(result, list) and self.streamed:
                merged = list(result)
                seen = {item.get("code") for item in merged
                        if isinstance(item, dict) and item.get("code")}
                for item in self.streamed:
                    code = item.get("code") if isinstance(item, dict) else None
                    if code and code not in seen:
                        merged.append(item)
                        seen.add(code)
                self.result = merged
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

    def append_streamed(self, stocks: List[Any]) -> None:
        """Append newly found stocks so the client can render them before the scan ends."""
        if stocks:
            self.streamed.extend(stocks)
            self.updated_at = time.time()

    def to_dict(self, since: int = 0) -> Dict[str, Any]:
        """Convert task to dictionary for API responses.

        Args:
            since: 客户端已收到的结果条数，只返回这个位置之后的新结果
        """
        # Sanitize result to handle NaN and Infinity values
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result": sanitize_task_result(self.result),
            "new_results": sanitize_task_result(self.streamed[since:]),
            "cursor": len(self.streamed),
            "scanned": self.scanned,
            "total": self.total,
            "found": self.found,
            "cancel_requested": self.cancel_requested,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at
        }


class TaskManager:
    """Manages background tasks and their statuses."""
    _instance = None
    _tasks: Dict[str, Task] = {}
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern to ensure only one TaskManager exists."""
        if cls._instance is None:
            cls._instance = super(TaskManager, cls).__new__(cls)
        return cls._instance

    def create_task(self) -> str:
        """Create a new task and return its ID."""
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = Task(task_id)
        return task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by its ID."""
        with self._lock:
            return self._tasks.get(task_id)

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

    def clean_old_tasks(self, max_age_seconds: int = 3600) -> None:
        """Remove tasks older than the specified age."""
        current_time = time.time()
        with self._lock:
            task_ids_to_remove = []
            for task_id, task in self._tasks.items():
                # Remove completed or failed tasks that are older than max_age_seconds
                if (task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED) and
                    task.completed_at and
                        current_time - task.completed_at > max_age_seconds):
                    task_ids_to_remove.append(task_id)

            for task_id in task_ids_to_remove:
                del self._tasks[task_id]

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks as dictionaries."""
        with self._lock:
            return [task.to_dict() for task in self._tasks.values()]


# Create a singleton instance
task_manager = TaskManager()
