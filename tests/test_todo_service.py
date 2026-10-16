from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest

from huiyang.domain.models import TaskVisibility
from huiyang.services.permissions import PermissionService


class FakeTaskRepository:
    def __init__(self) -> None:
        self.tasks = []

    async def add(self, task):
        self.tasks.append(task)
        return task


class FakeReminderRepository:
    def __init__(self) -> None:
        self.reminders = []

    async def add_many(self, reminders):
        self.reminders.extend(reminders)


def load_todos():
    try:
        return import_module("huiyang.services.todos")
    except ModuleNotFoundError:
        pytest.fail("Todo service is missing")


@pytest.mark.asyncio
async def test_create_team_task_builds_two_default_group_reminders() -> None:
    todos = load_todos()
    task_repo = FakeTaskRepository()
    reminder_repo = FakeReminderRepository()
    service = todos.TodoService(
        tasks=task_repo,
        reminders=reminder_repo,
        permissions=PermissionService("ou_admin"),
    )
    deadline = datetime(2026, 10, 9, 18, 0, tzinfo=UTC)

    task = await service.create(
        todos.CreateTaskCommand(
            title="完成首页",
            original_instruction="给小王建个任务，周五把首页做出来",
            creator_id=uuid4(),
            assignee_id=uuid4(),
            actor_feishu_user_id="ou_admin",
            assignee_feishu_user_id="ou_xiao",
            visibility=TaskVisibility.TEAM,
            source_chat_id="oc_group",
            deadline=deadline,
        )
    )

    assert task_repo.tasks == [task]
    assert [item.scheduled_for for item in reminder_repo.reminders] == [
        deadline - timedelta(hours=1),
        deadline,
    ]
    assert {item.destination for item in reminder_repo.reminders} == {"group"}
    assert {item.destination_chat_id for item in reminder_repo.reminders} == {
        "oc_group"
    }


@pytest.mark.asyncio
async def test_explicit_reminders_replace_defaults_and_personal_uses_private() -> None:
    todos = load_todos()
    task_repo = FakeTaskRepository()
    reminder_repo = FakeReminderRepository()
    service = todos.TodoService(
        tasks=task_repo,
        reminders=reminder_repo,
        permissions=PermissionService("ou_admin"),
    )
    deadline = datetime(2026, 10, 9, 18, 0, tzinfo=UTC)
    explicit = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)

    await service.create(
        todos.CreateTaskCommand(
            title="整理文档",
            original_instruction="周五中午提醒我整理文档",
            creator_id=uuid4(),
            assignee_id=uuid4(),
            actor_feishu_user_id="ou_xiao",
            assignee_feishu_user_id="ou_xiao",
            visibility=TaskVisibility.PERSONAL,
            deadline=deadline,
            reminder_times=[explicit],
        )
    )

    assert [item.scheduled_for for item in reminder_repo.reminders] == [explicit]
    assert reminder_repo.reminders[0].destination == "private"
    assert reminder_repo.reminders[0].destination_chat_id is None
