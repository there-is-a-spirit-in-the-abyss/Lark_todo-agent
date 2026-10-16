from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.domain.persistence import ConversationMemory
from huiyang.services.memory import MemoryAwareSecretary
from huiyang.services.secretary import IncomingMessage, SecretaryResponse


class FakeMemoryRepository:
    def __init__(self, relevant):
        self.items = relevant
        self.added = []

    async def relevant(self, *, chat_id, sender_id, now):
        return self.items

    async def add(self, memory):
        self.added.append(memory)
        return memory


class RecordingAgent:
    def __init__(self, response):
        self.response = response
        self.contexts = []

    async def handle(self, message, *, context):
        self.contexts.append(context)
        return self.response


@pytest.mark.asyncio
async def test_memory_wrapper_loads_references_and_records_personal_result() -> None:
    now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)
    prior = ConversationMemory(
        id=uuid4(),
        chat_id="oc_group",
        sender_id="ou_xiao",
        raw_message="刚才那个任务",
        resolved_task_ids=["task-old"],
        scope="personal",
        expires_at=now + timedelta(days=1),
        created_at=now,
    )
    task_id = uuid4()
    response = SecretaryResponse(
        text="已修改。",
        action=StructuredAction(
            action_type=ActionType.UPDATE_TASK,
            understanding="修改任务",
            task_id=task_id,
        ),
    )
    repository = FakeMemoryRepository([prior])
    delegate = RecordingAgent(response)
    service = MemoryAwareSecretary(delegate=delegate, memories=repository)
    message = IncomingMessage(
        sender_id="ou_xiao",
        chat_id="oc_group",
        chat_type="group",
        text="改到周五",
        received_at=now,
    )

    actual = await service.handle(message, context={"request_id": "r1"})

    assert actual == response
    assert delegate.contexts[0]["request_id"] == "r1"
    assert delegate.contexts[0]["references"][0]["resolved_task_ids"] == [
        "task-old"
    ]
    recorded = repository.added[0]
    assert recorded.resolved_task_ids == [str(task_id)]
    assert recorded.scope == "personal"
    assert recorded.expires_at == now + timedelta(days=7)
    assert recorded.result_data == {"response_text": "已修改。"}
