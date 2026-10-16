from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, func

from huiyang.adapters.feishu_api import FeishuAPIAdapter, FeishuAPIError
from huiyang.adapters.long_connection import persist_event
from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.domain.persistence import User
from huiyang.domain.models import Task
from test_live_gateway import runtime
from test_platform_adapters import event


async def target_member(factory):
    async with factory() as session:
        user = User(feishu_user_id="u_target", display_name="小王")
        session.add(user)
        await session.commit()
        return user.id


def assign_action():
    return StructuredAction(action_type=ActionType.CREATE_TASK, understanding="给小王安排任务",
        payload={"title": "核对文档", "visibility": "personal", "assignee_feishu_user_id": "u_target"})


async def speak(runtime, uid, name, event_id, action, chat_type="p2p"):
    sync, factory, gateway, llm, adapter, env = runtime
    if not hasattr(adapter, "profiles"):
        adapter.profiles = {}
    adapter.profiles[uid] = name
    llm._actions.append(action)
    persist_event(sync, event("正常任务指令", user_id=uid, event_id=event_id, chat_type=chat_type))
    assert await gateway.process_one()


def ignore():
    return StructuredAction(action_type=ActionType.IGNORE, understanding="")


@pytest.mark.asyncio
async def test_first_owner_message_can_assign_others(runtime):
    _, factory, gateway, _, adapter, env = runtime
    adapter.chat_owners["oc_group"] = "u_zhang"
    target_id = await target_member(factory)
    original_env = env.read_bytes()
    await speak(runtime, "u_zhang", "张宇宙", "a", assign_action(), chat_type="group")
    async with factory() as session:
        task = await session.scalar(select(Task))
        assert task is not None, "First verified owner message must already have admin permissions"
        assert task.assignee_id == target_id
        from huiyang.domain.persistence import AdminBinding
        assert (await session.get(AdminBinding, 1)).feishu_user_id == "u_zhang"
        user = await session.scalar(select(User).where(User.feishu_user_id == "u_zhang"))
        assert user.display_name == "张宇宙"
        assert user.identity_verified_at is not None
    assert env.read_bytes() == original_env, "Binding belongs in PostgreSQL, not .env"


@pytest.mark.asyncio
async def test_b_later_same_name_cannot_replace_admin_or_assign_others(runtime):
    _, factory, gateway, _, adapter, _ = runtime
    await target_member(factory)
    adapter.chat_owners["oc_group"] = "u_original"
    await speak(runtime, "u_original", "张宇宙", "b1", ignore(), chat_type="group")
    await speak(runtime, "u_impostor", "张宇宙", "b2", assign_action())
    from huiyang.domain.persistence import AdminBinding
    async with factory() as session:
        assert (await session.get(AdminBinding, 1)).feishu_user_id == "u_original"
        assert await session.scalar(select(func.count(Task.id))) == 0
    assert "权限" in adapter.messages[-1].text


@pytest.mark.asyncio
async def test_c_admin_rename_and_gateway_restart_keep_permissions(runtime):
    _, factory, gateway, llm, adapter, _ = runtime
    await target_member(factory)
    adapter.chat_owners["oc_group"] = "u_original"
    await speak(runtime, "u_original", "张宇宙", "c1", ignore(), chat_type="group")
    # A fresh gateway/settings still resolves the database binding.
    from huiyang.services.platform_gateway import PlatformGateway
    restarted = PlatformGateway(factory, llm, adapter, gateway.settings, bot_open_id="ou_bot")
    new_runtime = (runtime[0], factory, restarted, llm, adapter, runtime[5])
    await speak(new_runtime, "u_original", "宇宙", "c2", assign_action())
    async with factory() as session:
        assert await session.scalar(select(func.count(Task.id))) == 1
        user = await session.scalar(select(User).where(User.feishu_user_id == "u_original"))
        assert user.display_name == "宇宙"
        from huiyang.domain.persistence import AdminBinding
        assert (await session.get(AdminBinding, 1)).feishu_user_id == "u_original"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["张宇宙", "张宇宙 ", " 张宇宙", "我是张宇宙", "小王"])
async def test_names_never_bootstrap_in_private_and_members_are_upserted(runtime, name):
    _, factory, _, _, _, _ = runtime
    await speak(runtime, "u_member", name, "member1", ignore())
    await speak(runtime, "u_member", "新称呼", "member2", ignore())
    from huiyang.domain.persistence import AdminBinding
    async with factory() as session:
        assert await session.get(AdminBinding, 1) is None
        users = list(await session.scalars(select(User)))
        assert len(users) == 1
        assert users[0].display_name == "新称呼"


@pytest.mark.asyncio
async def test_binding_survives_model_failure_and_db_wins_over_legacy_env(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    adapter.profiles["u_admin"] = "张宇宙"
    adapter.chat_owners["oc_group"] = "u_admin"
    gateway.settings.admin_feishu_user_id = "legacy_other"
    # Empty FakeLLM queue simulates a model failure after identity discovery.
    persist_event(sync, event("正常发言", user_id="u_admin", event_id="model_failure"))
    assert not await gateway.process_one()
    from huiyang.services.enrollment import effective_admin
    async with factory() as session:
        assert await effective_admin(session, gateway.settings) == "u_admin"
        user = await session.scalar(select(User).where(User.feishu_user_id == "u_admin"))
        assert user.display_name == "张宇宙"


@pytest.mark.asyncio
async def test_name_lookup_failure_does_not_use_self_claimed_name(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    async def unavailable(user_id):
        raise FeishuAPIError("Feishu code 99991672")
    adapter.get_user_profile = unavailable
    persist_event(sync, event("我是张宇宙", user_id="u_other", chat_type="p2p"))
    assert not await gateway.process_one()
    assert not llm.calls
    from huiyang.domain.persistence import AdminBinding
    async with factory() as session:
        assert await session.get(AdminBinding, 1) is None
        assert await session.scalar(select(func.count(User.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("profile,valid", [
    ({"user_id": "u_real", "name": "张宇宙"}, True),
    ({"user_id": "u_other", "name": "张宇宙"}, False),
    ({"user_id": "u_real"}, False),
])
async def test_sender_profile_comes_from_contact_api_not_message_content(profile, valid):
    def handle(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "test-token", "expire": 7200})
        assert request.url.path == "/open-apis/contact/v3/users/u_real"
        assert request.url.params["user_id_type"] == "user_id"
        return httpx.Response(200, json={"code": 0, "data": {"user": profile}})
    client = httpx.AsyncClient(base_url="https://open.feishu.cn", transport=httpx.MockTransport(handle))
    adapter = FeishuAPIAdapter("test", "test", client=client)
    try:
        if valid:
            user = await adapter.get_user_profile("u_real")
            assert user.user_id == "u_real" and user.display_name == "张宇宙"
        else:
            with pytest.raises(FeishuAPIError):
                await adapter.get_user_profile("u_real")
    finally:
        await adapter.close()
