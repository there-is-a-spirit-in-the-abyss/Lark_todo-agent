from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huiyang.domain.models import Task, TaskStatus, TaskVisibility
from huiyang.services.permissions import PermissionService
from huiyang.services.todos import TodoService


class FakeTasks:
    def __init__(self, task):
        self.task = task

    async def get(self, task_id):
        return self.task if task_id == self.task.id else None

    async def save(self, task):
        return task


class FakeReminders:
    def __init__(self):
        self.added = []
        self.canceled = []

    async def add_many(self, reminders):
        self.added.extend(reminders)

    async def cancel_pending(self, task_id, *, canceled_at):
        self.canceled.append((task_id, canceled_at))


@pytest.mark.asyncio
async def test_update_deadline_replaces_pending_reminders_with_new_defaults() -> None:
    now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)
    old_deadline = now + timedelta(days=1)
    new_deadline = now + timedelta(days=2)
    task = Task(
        id=uuid4(),
        title="旧标题",
        original_instruction="修改任务",
        creator_id=uuid4(),
        assignee_id=uuid4(),
        visibility=TaskVisibility.TEAM,
        source_chat_id="oc_group",
        status=TaskStatus.TODO,
        deadline=old_deadline,
    )
    reminders = FakeReminders()
    service = TodoService(
        tasks=FakeTasks(task),
        reminders=reminders,
        permissions=PermissionService("ou_admin"),
    )

    updated = await service.update(
        task_id=task.id,
        actor_feishu_user_id="ou_admin",
        assignee_feishu_user_id="ou_xiao",
        changes={"title": "新标题", "deadline": new_deadline},
        now=now,
    )

    assert updated.title == "新标题"
    assert updated.deadline == new_deadline
    assert reminders.canceled == [(task.id, now)]
    assert [item.scheduled_for for item in reminders.added] == [
        new_deadline - timedelta(hours=1),
        new_deadline,
    ]
    assert {item.destination for item in reminders.added} == {"group"}
