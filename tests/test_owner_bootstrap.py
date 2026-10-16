from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select, func

from huiyang.adapters.feishu_api import FeishuAPIAdapter, FeishuAPIError
from huiyang.adapters.long_connection import persist_event
from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.domain.models import Task
from huiyang.domain.persistence import AdminBinding, User
from huiyang.services.permissions import PermissionService
from huiyang.services.enrollment import effective_admin
from test_live_gateway import runtime
from test_platform_adapters import event


def owner_api(adapter, uid="u_owner"):
    async def get_chat_owner(chat_id):
        assert chat_id == "oc_group"
        return SimpleNamespace(chat_id=chat_id, user_id=uid)
    adapter.get_chat_owner = get_chat_owner


def ignore():
    return StructuredAction(action_type=ActionType.IGNORE, understanding="")


@pytest.mark.asyncio
async def test_member_first_message_binds_absent_owner_not_sender(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    owner_api(adapter)
    # A coincidental name must not override the authoritative group owner.
    adapter.profiles["u_member"] = "张宇宙"
    original = env.read_bytes()
    async with factory() as session:
        session.add(User(feishu_user_id="u_target", display_name="小王"))
        await session.commit()
    llm._actions.append(StructuredAction(
        action_type=ActionType.CREATE_TASK, understanding="为别人派任务",
        payload={"title": "不应创建", "visibility": "personal", "assignee_feishu_user_id": "u_target"},
    ))
    persist_event(sync, event("给小王派任务", user_id="u_member"))
    assert await gateway.process_one()
    async with factory() as session:
        binding = await session.get(AdminBinding, 1)
        assert binding is not None
        assert binding.feishu_user_id == "u_owner"
        assert binding.source_chat_id == "oc_group"
        assert await session.scalar(select(User).where(User.feishu_user_id == "u_owner")) is not None
        assert await session.scalar(select(func.count(Task.id))) == 0
        permissions = PermissionService(await effective_admin(session))
        assert permissions.is_admin("u_owner")
        assert not permissions.is_admin("u_member")
    assert "权限" in adapter.messages[-1].text
    assert env.read_bytes() == original


@pytest.mark.asyncio
async def test_bound_admin_survives_owner_change_and_api_unavailable(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    owner_api(adapter)
    llm._actions.append(ignore())
    persist_event(sync, event("普通聊天", user_id="u_member", event_id="first"))
    assert await gateway.process_one()
    async def forbidden_lookup(chat_id):
        raise AssertionError("Already-bound deployments must never re-read group ownership")
    adapter.get_chat_owner = forbidden_lookup
    # Former owner remains admin after restart, rename and ownership transfer.
    from huiyang.services.platform_gateway import PlatformGateway
    gateway = PlatformGateway(factory, llm, adapter, gateway.settings, bot_open_id="ou_bot")
    adapter.profiles["u_owner"] = "改名后的用户"
    async with factory() as session:
        session.add(User(feishu_user_id="u_target", display_name="小王"))
        await session.commit()
    for uid, eid in [("u_new_owner", "new"), ("u_owner", "old")]:
        llm._actions.append(StructuredAction(
            action_type=ActionType.CREATE_TASK, understanding="派任务",
            payload={"title": eid, "visibility": "personal", "assignee_feishu_user_id": "u_target"},
        ))
        persist_event(sync, event("派任务", user_id=uid, event_id=eid))
        assert await gateway.process_one()
    async with factory() as session:
        assert (await session.get(AdminBinding, 1)).feishu_user_id == "u_owner"
        tasks = list(await session.scalars(select(Task)))
        assert len(tasks) == 1 and tasks[0].title == "old"
        user = await session.scalar(select(User).where(User.feishu_user_id == "u_owner"))
        assert user.display_name == "改名后的用户"


@pytest.mark.asyncio
async def test_private_zhang_message_cannot_bootstrap(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    async def forbidden_lookup(chat_id):
        raise AssertionError("Private chats must not discover a group owner")
    adapter.get_chat_owner = forbidden_lookup
    adapter.profiles["u_zhang"] = "张宇宙"
    llm._actions.append(ignore())
    persist_event(sync, event("我是张宇宙", user_id="u_zhang", chat_type="p2p"))
    assert await gateway.process_one()
    async with factory() as session:
        assert await session.get(AdminBinding, 1) is None


@pytest.mark.asyncio
async def test_group_api_failure_cannot_fall_back_to_name_or_sender(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    async def denied(chat_id):
        raise FeishuAPIError("Feishu code 99991672")
    adapter.get_chat_owner = denied
    adapter.profiles["u_member"] = "张宇宙"
    llm._actions.append(ignore())
    persist_event(sync, event("普通消息", user_id="u_member"))
    assert not await gateway.process_one()
    async with factory() as session:
        assert await session.get(AdminBinding, 1) is None
    assert not llm.calls


@pytest.mark.asyncio
async def test_owner_binding_does_not_require_sender_or_owner_name(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    owner_api(adapter)
    async def no_contact_permission(uid):
        raise FeishuAPIError("Contact permission denied")
    adapter.get_user_profile = no_contact_permission
    persist_event(sync, event("普通消息", user_id="u_member"))
    assert not await gateway.process_one()  # Business waits for member profile.
    async with factory() as session:
        assert (await session.get(AdminBinding, 1)).feishu_user_id == "u_owner"
        owner = await session.scalar(select(User).where(User.feishu_user_id == "u_owner"))
        assert owner.identity_verified_at is None
    assert not llm.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("data,valid", [
    ({"owner_id": "u_owner", "owner_id_type": "user_id", "chat_mode": "group"}, True),
    ({"owner_id": "ou_owner", "owner_id_type": "open_id", "chat_mode": "group"}, False),
    ({"owner_id": "", "owner_id_type": "user_id", "chat_mode": "group"}, False),
    ({"owner_id": "u_owner", "chat_mode": "group"}, False),
    ({"owner_id": "u_owner", "owner_id_type": "user_id", "chat_mode": "p2p"}, False),
    ({"owner_id_type": "user_id", "chat_mode": "group"}, False),
])
async def test_group_api_requests_and_validates_real_user_id(data, valid):
    def handle(request):
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "test", "expire": 7200})
        assert request.url.path == "/open-apis/im/v1/chats/oc_group"
        assert request.url.params["user_id_type"] == "user_id"
        return httpx.Response(200, json={"code": 0, "data": data})
    client = httpx.AsyncClient(base_url="https://open.feishu.cn", transport=httpx.MockTransport(handle))
    adapter = FeishuAPIAdapter("test", "test", client=client)
    try:
        if valid:
            owner = await adapter.get_chat_owner("oc_group")
            assert owner.user_id == "u_owner" and owner.chat_id == "oc_group"
        else:
            with pytest.raises(FeishuAPIError):
                await adapter.get_chat_owner("oc_group")
    finally:
        await adapter.close()
