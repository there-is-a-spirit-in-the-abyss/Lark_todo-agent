from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.domain.models import Task, TaskStatus, TaskVisibility
from huiyang.services.executor import BusinessActionExecutor, UserIdentity
from huiyang.services.secretary import IncomingMessage


class FakeUsers:
    def __init__(self, identities):
        self.identities = identities

    async def by_feishu_id(self, feishu_user_id):
        return self.identities.get(feishu_user_id)

    async def by_id(self, user_id):
        return next(
            (item for item in self.identities.values() if item.id == user_id),
            None,
        )


class FakeTasks:
    def __init__(self):
        self.active = {}

    async def get(self, task_id):
        for tasks in self.active.values():
            for task in tasks:
                if task.id == task_id:
                    return task
        return None

    async def list_active_by_assignee(self, assignee_id):
        return self.active.get(assignee_id, [])


class FakeTodos:
    def __init__(self, tasks):
        self.tasks = tasks
        self.created = []

    async def create(self, command):
        self.created.append(command)
        task = Task(
            id=uuid4(),
            title=command.title,
            original_instruction=command.original_instruction,
            creator_id=command.creator_id,
            assignee_id=command.assignee_id,
            visibility=command.visibility,
            source_chat_id=command.source_chat_id,
            status=TaskStatus.TODO,
            deadline=command.deadline,
        )
        self.tasks.active.setdefault(command.assignee_id, []).append(task)
        return task


@pytest.mark.asyncio
async def test_create_action_maps_identity_and_returns_assignee_active_todos() -> None:
    admin = UserIdentity(uuid4(), "ou_admin", "管理员")
    assignee = UserIdentity(uuid4(), "ou_xiao", "小王")
    users = FakeUsers({"ou_admin": admin, "ou_xiao": assignee})
    tasks = FakeTasks()
    todos = FakeTodos(tasks)
    executor = BusinessActionExecutor(todo_service=todos, tasks=tasks, users=users)
    deadline = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    action = StructuredAction(
        action_type=ActionType.CREATE_TASK,
        understanding="给小王创建完成首页",
        payload={
            "title": "完成首页",
            "assignee_feishu_user_id": "ou_xiao",
            "visibility": "team",
            "deadline": deadline.isoformat(),
        },
    )
    message = IncomingMessage(
        sender_id="ou_admin",
        chat_id="oc_group",
        chat_type="group",
        text="给小王建任务",
        received_at=datetime(2026, 10, 4, 5, 0, tzinfo=UTC),
    )

    result = await executor.execute(action, message)

    assert todos.created[0].creator_id == admin.id
    assert todos.created[0].assignee_id == assignee.id
    assert todos.created[0].source_chat_id == "oc_group"
    assert todos.created[0].deadline == deadline
    assert result.outcome == "已创建任务「完成首页」。"
    assert result.affected_todos["小王"][0].title == "完成首页"


@pytest.mark.asyncio
async def test_list_action_is_always_scoped_to_sender() -> None:
    member = UserIdentity(uuid4(), "ou_xiao", "小王")
    users = FakeUsers({"ou_xiao": member})
    tasks = FakeTasks()
    tasks.active[member.id] = [
        Task(
            id=uuid4(),
            title="自己的任务",
            original_instruction="自己的任务",
            creator_id=member.id,
            assignee_id=member.id,
            visibility=TaskVisibility.PERSONAL,
            status=TaskStatus.TODO,
        )
    ]
    executor = BusinessActionExecutor(
        todo_service=FakeTodos(tasks),
        tasks=tasks,
        users=users,
    )

    result = await executor.execute(
        StructuredAction(
            action_type=ActionType.LIST_TASKS,
            understanding="查看我的任务",
        ),
        IncomingMessage(
            sender_id="ou_xiao",
            chat_id="oc_group",
            chat_type="group",
            text="我的任务",
            received_at=datetime(2026, 10, 4, 5, 0, tzinfo=UTC),
        ),
    )

    assert result.outcome == "当前共有 1 个进行中的任务。"
    assert [item.title for item in result.affected_todos["小王"]] == ["自己的任务"]
