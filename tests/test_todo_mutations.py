from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huiyang.domain.models import Task, TaskStatus, TaskVisibility
from huiyang.services.permissions import PermissionService
from huiyang.services.todos import TodoService


class FakeTaskRepository:
    def __init__(self, task: Task) -> None:
        self.task = task
        self.deleted = []

    async def add(self, task: Task) -> Task:
        self.task = task
        return task

    async def get(self, task_id):
        return self.task if self.task.id == task_id else None

    async def save(self, task: Task) -> Task:
        self.task = task
        return task

    async def delete(self, task_id) -> None:
        self.deleted.append(task_id)


class FakeReminderRepository:
    def __init__(self) -> None:
        self.canceled = []

    async def add_many(self, reminders) -> None:
        pass

    async def cancel_pending(self, task_id, *, canceled_at) -> None:
        self.canceled.append((task_id, canceled_at))


def make_task() -> Task:
    return Task(
        id=uuid4(),
        title="完成首页",
        original_instruction="完成首页",
        creator_id=uuid4(),
        assignee_id=uuid4(),
        visibility=TaskVisibility.TEAM,
        status=TaskStatus.IN_PROGRESS,
    )


@pytest.mark.asyncio
async def test_completing_task_cancels_pending_reminders() -> None:
    task = make_task()
    tasks = FakeTaskRepository(task)
    reminders = FakeReminderRepository()
    service = TodoService(
        tasks=tasks,
        reminders=reminders,
        permissions=PermissionService("ou_admin"),
    )
    now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)

    updated = await service.set_status(
        task_id=task.id,
        status=TaskStatus.COMPLETED,
        actor_feishu_user_id="ou_admin",
        assignee_feishu_user_id="ou_xiao",
        now=now,
    )

    assert updated.status is TaskStatus.COMPLETED
    assert reminders.canceled == [(task.id, now)]


@pytest.mark.asyncio
async def test_delete_is_hard_and_cancels_pending_reminders_first() -> None:
    task = make_task()
    tasks = FakeTaskRepository(task)
    reminders = FakeReminderRepository()
    service = TodoService(
        tasks=tasks,
        reminders=reminders,
        permissions=PermissionService("ou_admin"),
    )
    now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)

    await service.delete(
        task_id=task.id,
        actor_feishu_user_id="ou_admin",
        assignee_feishu_user_id="ou_xiao",
        now=now,
    )

    assert reminders.canceled == [(task.id, now)]
    assert tasks.deleted == [task.id]
