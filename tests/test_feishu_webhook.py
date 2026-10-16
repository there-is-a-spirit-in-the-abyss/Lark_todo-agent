import json
from datetime import UTC, datetime

import pytest

from huiyang.adapters.feishu import MockFeishuAdapter
from huiyang.adapters.webhook import FeishuWebhookGateway
from huiyang.services.secretary import SecretaryResponse
from huiyang.agent.schemas import ActionType, StructuredAction


class FakeAgent:
    def __init__(self) -> None:
        self.messages = []

    async def handle(self, message, *, context):
        self.messages.append((message, context))
        return SecretaryResponse(
            text="已记录。",
            action=StructuredAction(
                action_type=ActionType.CREATE_TASK,
                understanding="创建任务",
            ),
        )


@pytest.mark.asyncio
async def test_url_verification_requires_configured_token() -> None:
    gateway = FeishuWebhookGateway(
        verification_token="expected",
        agent=FakeAgent(),
        adapter=MockFeishuAdapter(),
    )

    assert await gateway.process(
        {"type": "url_verification", "token": "expected", "challenge": "hello"}
    ) == {"challenge": "hello"}

    with pytest.raises(PermissionError):
        await gateway.process(
            {"type": "url_verification", "token": "wrong", "challenge": "hello"}
        )


@pytest.mark.asyncio
async def test_message_event_is_normalized_replied_and_deduplicated() -> None:
    agent = FakeAgent()
    adapter = MockFeishuAdapter()
    gateway = FeishuWebhookGateway(
        verification_token="expected",
        agent=agent,
        adapter=adapter,
        now=lambda: datetime(2026, 10, 4, 5, 0, tzinfo=UTC),
    )
    payload = {
        "header": {
            "token": "expected",
            "event_id": "event-1",
            "event_type": "im.message.receive_v1",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "ou_xiao"}},
            "message": {
                "chat_id": "oc_group",
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": "周五完成首页"}),
            },
        },
    }

    assert await gateway.process(payload) == {"code": 0}
    assert await gateway.process(payload) == {"code": 0}

    assert len(agent.messages) == 1
    message, context = agent.messages[0]
    assert message.sender_id == "ou_xiao"
    assert message.chat_id == "oc_group"
    assert message.chat_type == "group"
    assert message.text == "周五完成首页"
    assert context == {}
    assert adapter.messages[0].channel == "group"
    assert adapter.messages[0].target_id == "oc_group"
    assert adapter.messages[0].text == "已记录。"
