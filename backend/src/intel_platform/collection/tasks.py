from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    PROGRESS = "PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"


class CollectionTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    pir: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    documents_acquired: int = 0
    plan: list[dict] = Field(default_factory=list)
    results: list[dict] = Field(default_factory=list)
    error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectionManager:
    def __init__(self):
        self._tasks: dict[str, CollectionTask] = {}

    def create_task(self, project_id: str, pir: str = "", plan: list[dict] | None = None) -> CollectionTask:
        task = CollectionTask(project_id=project_id, pir=pir, plan=plan or [])
        self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> CollectionTask | None:
        return self._tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs) -> CollectionTask | None:
        task = self._tasks.get(task_id)
        if not task:
            return None
        for k, v in kwargs.items():
            if hasattr(task, k):
                setattr(task, k, v)
        task.updated_at = datetime.now(timezone.utc)
        return task

    def list_tasks(self, project_id: str | None = None) -> list[CollectionTask]:
        tasks = list(self._tasks.values())
        if project_id:
            tasks = [t for t in tasks if t.project_id == project_id]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status in (TaskStatus.PENDING, TaskStatus.STARTED, TaskStatus.PROGRESS):
            task.status = TaskStatus.REVOKED
            task.updated_at = datetime.now(timezone.utc)
            return True
        return False
