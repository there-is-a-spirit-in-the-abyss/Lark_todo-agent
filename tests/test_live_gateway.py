import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import create_engine

from huiyang.adapters.feishu import MockFeishuAdapter
from huiyang.adapters.long_connection import persist_event
from huiyang.agent.llm import FakeLLMAdapter
from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.config import Settings
from huiyang.domain.models import Base, Task
from huiyang.domain.persistence import User, ConversationMemory
from huiyang.domain.platform import ChatObservation, FeishuInbox
from huiyang.services.platform_gateway import PlatformGateway
from test_platform_adapters import event


@pytest_asyncio.fixture
async def runtime(tmp_path):
    path = tmp_path / "db.sqlite"
    sync_engine = create_engine("sqlite:///" + str(path))
    Base.metadata.create_all(sync_engine)
    engine = create_async_engine("sqlite+aiosqlite:///" + str(path))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    env = tmp_path / ".env"
    env.write_text("ADMIN_FEISHU_USER_ID=\nFEISHU_APP_SECRET=keep\n")
    settings = Settings(_env_file=None, env_path=str(env), app_timezone="Asia/Shanghai")
    llm = FakeLLMAdapter([])
    adapter = MockFeishuAdapter()
    adapter.chat_owners["oc_group"] = "u_group_owner"
    gateway = PlatformGateway(factory, llm, adapter, settings, bot_open_id="ou_bot")
    yield sync_engine, factory, gateway, llm, adapter, env
    await engine.dispose()
    sync_engine.dispose()


@pytest.mark.asyncio
async def test_normal_chat_is_context_not_task_and_duplicate_survives_restart(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    llm._actions.append(StructuredAction(action_type=ActionType.IGNORE, understanding="普通聊天"))
    payload = event("首页采用昨天的布局")
    persist_event(sync, payload)
    persist_event(sync, payload)
    assert await gateway.process_one()
    persist_event(sync, payload)
    assert not await gateway.process_one()
    async with factory() as session:
        assert await session.scalar(select(func.count(Task.id))) == 0
        assert await session.scalar(select(func.count(ChatObservation.message_id))) == 1
        assert await session.scalar(select(func.count(User.id))) == 2
    assert adapter.messages == []
    assert llm.calls[0][1]["recent_chat"][0]["text"] == "首页采用昨天的布局"


@pytest.mark.asyncio
async def test_self_registration_cannot_spoof_feishu_name(runtime):
    from huiyang.domain.persistence import AdminBinding
    sync, factory, gateway, llm, adapter, env = runtime
    adapter.profiles["u_impostor"] = "小王"
    persist_event(sync, event("登记 张宇宙", user_id="u_impostor", chat_type="p2p"))
    assert await gateway.process_one()
    async with factory() as session:
        assert await session.get(AdminBinding, 1) is None
        user = await session.scalar(select(User))
        assert user.display_name == "小王"
    assert "ADMIN_FEISHU_USER_ID=\n" in env.read_text()


@pytest.mark.asyncio
async def test_delivery_retry_does_not_repeat_task_mutation(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    llm._actions.append(StructuredAction(
        action_type=ActionType.CREATE_TASK, understanding="创建我的任务",
        payload={"title": "整理文档", "visibility": "personal"},
    ))
    persist_event(sync, event("帮我记录整理文档", chat_type="p2p"))
    original = adapter.send_private
    async def failing(*args, **kwargs):
        raise ConnectionError("outbound unavailable")
    adapter.send_private = failing
    assert not await gateway.process_one()
    async with factory() as session:
        assert await session.scalar(select(func.count(Task.id))) == 1
        row = await session.get(FeishuInbox, "evt-1")
        assert row.state == "ready"
        row.retry_at = None
        await session.commit()
    adapter.send_private = original
    assert await gateway.process_one()
    assert len(llm.calls) == 1
    assert len(adapter.messages) == 1


@pytest.mark.asyncio
async def test_personal_context_not_visible_to_other_group_or_member(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    for idx, (uid, kind, text) in enumerate([
        ("u_a", "p2p", "私人安排"), ("u_b", "group", "普通群聊")
    ]):
        llm._actions.append(StructuredAction(action_type=ActionType.IGNORE, understanding=""))
        persist_event(sync, event(text, event_id=str(idx), user_id=uid, chat_type=kind))
        await gateway.process_one()
    # Test fixture intentionally reuses chat_id; real p2p and group ids differ.
    # Require the query also to scope by chat_type, not merely the ID.
    assert "私人安排" not in str(llm.calls[-1][1]["recent_chat"])


@pytest.mark.asyncio
async def test_member_cannot_assign_other_user_and_raw_event_is_canonical(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    persist_event(sync, event("登记 小王", event_id="reg", user_id="u_other", chat_type="p2p"))
    await gateway.process_one()
    llm._actions.append(StructuredAction(action_type=ActionType.CREATE_TASK, understanding="给小王派任务",
        payload={"title": "越权任务", "assignee_feishu_user_id": "u_other", "visibility": "personal"}))
    persist_event(sync, event("给小王建个任务", event_id="deny", user_id="u_member", chat_type="p2p"))
    await gateway.process_one()
    async with factory() as session:
        assert await session.scalar(select(func.count(Task.id))) == 0
    assert "权限" in adapter.messages[-1].text
