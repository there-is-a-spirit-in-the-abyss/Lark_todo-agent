from datetime import UTC, datetime
from importlib import import_module

import pytest


class FakeInterpreter:
    def __init__(self, action) -> None:
        self.action = action

    async def interpret(self, message, context):
        return self.action


class FakeExecutor:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = []

    async def execute(self, action, message):
        self.calls.append((action, message))
        return self.result


def load_agent_modules():
    try:
        schemas = import_module("huiyang.agent.schemas")
        secretary = import_module("huiyang.services.secretary")
        return schemas, secretary
    except ModuleNotFoundError:
        pytest.fail("Secretary Agent modules are missing")


@pytest.mark.asyncio
async def test_ambiguous_action_only_asks_the_unresolved_question() -> None:
    schemas, secretary = load_agent_modules()
    action = schemas.StructuredAction(
        action_type=schemas.ActionType.CREATE_TASK,
        understanding="给小王创建「完成首页」，截止周五",
        ambiguity=schemas.Ambiguity(
            field="project_id",
            question="这是哪个项目？",
        ),
    )
    executor = FakeExecutor(result=None)
    service = secretary.SecretaryAgent(FakeInterpreter(action), executor)

    response = await service.handle(
        secretary.IncomingMessage(
            sender_id="ou_admin",
            chat_id="oc_group",
            chat_type="group",
            text="给小王建个任务，周五把首页做出来",
            received_at=datetime(2026, 10, 4, 5, 0, tzinfo=UTC),
        ),
        context={},
    )

    assert executor.calls == []
    assert response.text == (
        "我理解你要给小王创建「完成首页」，截止周五。"
        "目前不能确定属于哪个项目，这是哪个项目？"
    )


@pytest.mark.asyncio
async def test_clear_mutation_executes_then_lists_affected_assignee_todos() -> None:
    schemas, secretary = load_agent_modules()
    action = schemas.StructuredAction(
        action_type=schemas.ActionType.UPDATE_TASK,
        understanding="将小王的「完成首页」截止时间改为周五",
    )
    result = secretary.ExecutionResult(
        outcome="已修改。",
        affected_todos={
            "小王": [
                secretary.TodoView(title="完成首页", deadline_text="周五", status="进行中"),
                secretary.TodoView(title="测试机器人", deadline_text="下周一", status="待办"),
            ]
        },
    )
    executor = FakeExecutor(result)
    service = secretary.SecretaryAgent(FakeInterpreter(action), executor)
    message = secretary.IncomingMessage(
        sender_id="ou_admin",
        chat_id="oc_group",
        chat_type="group",
        text="小王那个首页改到周五",
        received_at=datetime(2026, 10, 4, 5, 0, tzinfo=UTC),
    )

    response = await service.handle(message, context={})

    assert executor.calls == [(action, message)]
    assert "已修改。" in response.text
    assert "我理解并执行的是：\n将小王的「完成首页」截止时间改为周五。" in response.text
    assert "小王当前任务：" in response.text
    assert "1. 完成首页｜周五｜进行中" in response.text
    assert "2. 测试机器人｜下周一｜待办" in response.text
