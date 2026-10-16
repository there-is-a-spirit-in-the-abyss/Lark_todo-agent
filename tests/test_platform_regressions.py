from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.domain.models import Task, TaskStatus, TaskVisibility
from huiyang.domain.persistence import User, Reminder, ConversationMemory
from huiyang.domain.platform import FeishuInbox
from huiyang.adapters.long_connection import persist_event
from test_platform_adapters import event
from test_live_gateway import runtime


@pytest.mark.asyncio
async def test_group_context_uses_prior_other_member_message(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    for idx, (uid, text) in enumerate([("u_a", "首页采用蓝色"), ("u_b", "@_user_1 按刚才他说的记录任务")]):
        llm._actions.append(StructuredAction(action_type=ActionType.IGNORE, understanding=""))
        persist_event(sync, event(text, user_id=uid, event_id=str(idx)))
        await gateway.process_one()
    context = llm.calls[-1][1]
    assert [item["sender_user_id"] for item in context["recent_chat"]] == ["u_a", "u_b"]
    assert context["recent_chat"][0]["text"] == "首页采用蓝色"


@pytest.mark.asyncio
async def test_admin_reassignment_lists_both_people_and_reroutes_existing_reminder(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    gateway.settings.admin_feishu_user_id = "u_admin"
    deadline = datetime.now(UTC) + timedelta(days=2)
    async with factory() as session:
        first = User(id=uuid4(), feishu_user_id="u_first", display_name="小王")
        second = User(id=uuid4(), feishu_user_id="u_second", display_name="小李")
        task = Task(id=uuid4(), title="首页", original_instruction="做首页",
            creator_id=first.id, assignee_id=first.id, visibility=TaskVisibility.PERSONAL,
            status=TaskStatus.TODO, deadline=deadline)
        session.add_all([first, second, task])
        reminder = Reminder(id=uuid4(), task_id=task.id, scheduled_for=deadline, kind="default",
                            destination="private")
        session.add(reminder)
        await session.commit()
        task_id, second_id = task.id, second.id
    llm._actions.append(StructuredAction(action_type=ActionType.UPDATE_TASK, task_id=task_id,
        understanding="将首页交给小李", payload={"assignee_feishu_user_id": "u_second"}))
    persist_event(sync, event("把首页交给小李", user_id="u_admin", chat_type="p2p"))
    assert await gateway.process_one()
    assert "小王当前任务" in adapter.messages[-1].text
    assert "小李当前任务" in adapter.messages[-1].text
    async with factory() as session:
        updated = await session.get(Task, task_id)
        assert updated.assignee_id == second_id


@pytest.mark.asyncio
async def test_explicit_reminder_only_edit_and_hard_delete(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    deadline = datetime.now(UTC) + timedelta(days=3)
    llm._actions.append(StructuredAction(action_type=ActionType.CREATE_TASK, understanding="创建",
        payload={"title": "文档", "visibility": "personal", "deadline": deadline.isoformat()}))
    persist_event(sync, event("记个任务", chat_type="p2p"))
    await gateway.process_one()
    async with factory() as session:
        task = await session.scalar(select(Task))
        task_id = task.id
    custom = deadline - timedelta(hours=5)
    llm._actions.append(StructuredAction(action_type=ActionType.UPDATE_TASK, task_id=task_id,
        understanding="改提醒", payload={"reminder_times": [custom.isoformat()]}))
    persist_event(sync, event("提前5小时提醒", event_id="update", chat_type="p2p"))
    assert await gateway.process_one()
    async with factory() as session:
        active = list(await session.scalars(select(Reminder).where(Reminder.canceled_at.is_(None))))
        assert len(active) == 1
        assert active[0].kind == "custom"
    llm._actions.append(StructuredAction(action_type=ActionType.DELETE_TASK, task_id=task_id,
        understanding="删除"))
    persist_event(sync, event("删除那个", event_id="delete", chat_type="p2p"))
    assert await gateway.process_one()
    async with factory() as session:
        assert await session.get(Task, task_id) is None


@pytest.mark.asyncio
async def test_list_order_is_saved_for_later_second_reference(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    for idx in range(2):
        llm._actions.append(StructuredAction(action_type=ActionType.CREATE_TASK, understanding="创建",
            payload={"title": f"任务{idx}", "visibility": "personal"}))
        persist_event(sync, event("创建", event_id=str(idx), chat_type="p2p"))
        await gateway.process_one()
    llm._actions.append(StructuredAction(action_type=ActionType.LIST_TASKS, understanding="查看我的任务"))
    persist_event(sync, event("我的任务", event_id="list", chat_type="p2p"))
    await gateway.process_one()
    async with factory() as session:
        memory = await session.scalar(select(ConversationMemory).where(
            ConversationMemory.raw_message == "我的任务"))
        assert len(memory.resolved_task_ids) == 2


@pytest.mark.asyncio
async def test_normal_group_message_can_discover_admin_without_binding_command(runtime):
    from huiyang.domain.persistence import AdminBinding
    sync, factory, gateway, llm, adapter, env = runtime
    adapter.profiles["u_a"] = "张宇宙"
    adapter.chat_owners["oc_group"] = "u_a"
    llm._actions.append(StructuredAction(action_type=ActionType.IGNORE, understanding=""))
    persist_event(sync, event("今天大家辛苦了", user_id="u_a"))
    assert await gateway.process_one()
    async with factory() as session:
        assert (await session.get(AdminBinding, 1)).feishu_user_id == "u_a"
    assert adapter.messages == []
    assert "ADMIN_FEISHU_USER_ID=\n" in env.read_text()
