from datetime import UTC, datetime
from importlib import import_module

import pytest

from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.services.secretary import IncomingMessage


@pytest.mark.asyncio
async def test_fake_llm_returns_scripted_action_and_records_context() -> None:
    try:
        llm = import_module("huiyang.agent.llm")
    except ModuleNotFoundError:
        pytest.fail("LLM adapter is missing")

    expected = StructuredAction(
        action_type=ActionType.LIST_TASKS,
        understanding="查看我的 Todo",
    )
    adapter = llm.FakeLLMAdapter([expected])
    message = IncomingMessage(
        sender_id="ou_xiao",
        chat_id="oc_group",
        chat_type="group",
        text="我的任务",
        received_at=datetime(2026, 10, 4, 5, 0, tzinfo=UTC),
    )
    context = {"references": [{"resolved_task_ids": ["task-1"]}]}

    actual = await adapter.interpret(message, context)

    assert actual == expected
    assert adapter.calls == [(message, context)]
