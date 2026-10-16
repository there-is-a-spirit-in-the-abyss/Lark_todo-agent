import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from huiyang.adapters.feishu import MockFeishuAdapter
from huiyang.adapters.webhook import FeishuWebhookGateway
from huiyang.agent.llm import FakeLLMAdapter
from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.domain.models import Base, Task
from huiyang.domain.persistence import ConversationMemory, Reminder, User
from huiyang.services.runtime import SessionSecretary


@pytest.mark.asyncio
async def test_mock_event_runs_through_agent_database_and_reply() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    admin_id, assignee_id = uuid4(), uuid4()
    async with factory() as session:
        session.add_all(
            [
                User(
                    id=admin_id,
                    feishu_user_id="ou_admin",
                    display_name="管理员",
                ),
                User(
                    id=assignee_id,
                    feishu_user_id="ou_xiao",
                    display_name="小王",
                ),
            ]
        )
        await session.commit()

    deadline = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    interpreter = FakeLLMAdapter(
        [
            StructuredAction(
                action_type=ActionType.CREATE_TASK,
                understanding="给小王创建「完成首页」",
                payload={
                    "title": "完成首页",
                    "assignee_feishu_user_id": "ou_xiao",
                    "visibility": "team",
                    "deadline": deadline.isoformat(),
                },
            )
        ]
    )
    secretary = SessionSecretary(
        session_factory=factory,
        interpreter=interpreter,
        admin_feishu_user_id="ou_admin",
    )
    adapter = MockFeishuAdapter()
    gateway = FeishuWebhookGateway(
        verification_token="token",
        agent=secretary,
        adapter=adapter,
        now=lambda: datetime(2026, 10, 4, 5, 0, tzinfo=UTC),
    )

    await gateway.process(
        {
            "header": {
                "token": "token",
                "event_id": "event-1",
                "event_type": "im.message.receive_v1",
            },
            "event": {
                "sender": {"sender_id": {"open_id": "ou_admin"}},
                "message": {
                    "chat_id": "oc_group",
                    "chat_type": "group",
                    "message_type": "text",
                    "content": json.dumps({"text": "给小王建任务"}),
                },
            },
        }
    )

    assert "已创建任务「完成首页」。" in adapter.messages[0].text
    assert "小王当前任务：" in adapter.messages[0].text
    async with factory() as session:
        task = await session.scalar(select(Task))
        assert task is not None
        assert task.assignee_id == assignee_id
        assert await session.scalar(select(func.count(Reminder.id))) == 2
        assert await session.scalar(select(func.count(ConversationMemory.id))) == 1

    await engine.dispose()
