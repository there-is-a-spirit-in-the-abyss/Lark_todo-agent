from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from huiyang.adapters.long_connection import persist_event
from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.domain.models import Task, TaskVisibility
from huiyang.domain.persistence import AdminBinding, Project, Reminder, User, ConversationMemory
from huiyang.domain.platform import FeishuInbox
from huiyang.services.background import BackgroundJobs
from test_live_gateway import runtime
from test_platform_adapters import event


@pytest.mark.asyncio
async def test_group_entry_requires_bot_mention_and_keyword_without_llm_or_admin(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    gateway.settings.team_web_enabled = True
    gateway.settings.team_public_url = "https://team.test"
    for index, (text, mentioned, expected) in enumerate([
        ("团队任务", False, 0), ("创建任务", True, 0),
        ("@_user_1 团队任务", True, 1), ("@_user_1 团队TODO", True, 2),
    ]):
        payload = event(text, event_id=str(index))
        if not mentioned:
            payload["event"]["message"]["mentions"] = []
        persist_event(sync, payload)
        assert await gateway.process_one()
        assert len(adapter.messages) == expected
    assert not llm.calls
    assert "https://team.test/team/oc_group" in adapter.messages[-1].text
    async with factory() as session:
        assert await session.get(AdminBinding, 1) is None
        assert await session.scalar(select(Task)) is None


@pytest.mark.asyncio
async def test_legacy_group_outbox_and_weekly_sends_are_suppressed(runtime):
    _, factory, gateway, _, adapter, _ = runtime
    gateway.settings.team_web_enabled = True
    async with factory() as session:
        session.add(FeishuInbox(event_id="legacy", payload={}, state="ready",
                                response={"target": "oc_group", "private": False, "text": "old"}))
        session.add(Project(name="旧项目", summary_chat_id="oc_group"))
        await session.commit()
    assert await gateway.process_one()
    await BackgroundJobs(factory, adapter, gateway.settings).weekly_summary()
    assert adapter.messages == []


@pytest.mark.asyncio
async def test_personal_queries_mutations_and_reminders_ignore_legacy_team(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    gateway.settings.team_web_enabled = True
    uid = uuid4()
    personal, team = uuid4(), uuid4()
    async with factory() as session:
        session.add(User(id=uid, feishu_user_id="u_real", display_name="本人"))
        await session.flush()
        for task_id, visibility in [(personal, TaskVisibility.PERSONAL), (team, TaskVisibility.TEAM)]:
            session.add(Task(id=task_id, title=visibility.value, original_instruction="", creator_id=uid,
                             assignee_id=uid, visibility=visibility))
            await session.flush()
            session.add(Reminder(task_id=task_id, scheduled_for=datetime(2020,1,1,tzinfo=UTC),
                                 kind="custom", destination="private"))
        await session.commit()
    old_project=uuid4()
    async with factory() as session:
        session.add(Project(id=old_project,name="旧团队项目"))
        await session.flush()
        session.add_all([
            ConversationMemory(chat_id="oc_group",sender_id="u_real",raw_message="旧团队",
                action_data={"action_type":"list_tasks","payload":{}},resolved_task_ids=[str(team)],
                result_data={"response_text":"旧团队任务"},scope="personal"),
            ConversationMemory(chat_id="oc_group",sender_id="u_real",raw_message="个人",
                action_data={"action_type":"list_tasks","payload":{}},resolved_task_ids=[str(personal)],
                result_data={"response_text":"个人任务"},scope="personal"),
            ConversationMemory(chat_id="oc_group",sender_id="u_real",raw_message="团队周报",
                action_data={"action_type":"weekly_summary","payload":{}},resolved_task_ids=[],
                resolved_project_id=old_project,result_data={"response_text":"旧团队周报"},scope="project"),
        ])
        await session.commit()
    llm._actions.append(StructuredAction(action_type=ActionType.LIST_TASKS, understanding="我的任务"))
    persist_event(sync, event("我的任务", chat_type="p2p"))
    assert await gateway.process_one()
    assert [t["visibility"] for t in llm.calls[0][1]["tasks"]] == ["personal"]
    assert [r["raw_message"] for r in llm.calls[0][1]["references"]] == ["个人"]
    assert llm.calls[0][1]["projects"] == []
    assert "team" not in adapter.messages[-1].text
    llm._actions.append(StructuredAction(action_type=ActionType.DELETE_TASK, task_id=team, understanding="删除"))
    persist_event(sync, event("删除", chat_type="p2p", event_id="delete"))
    await gateway.process_one()
    async with factory() as session:
        assert await session.get(Task, team) is not None
    adapter.messages.clear()
    await BackgroundJobs(factory, adapter, gateway.settings).reminders()
    assert len(adapter.messages) == 1 and "personal" in adapter.messages[0].text


@pytest.mark.asyncio
async def test_new_private_project_remains_available_for_next_message(runtime):
    sync, factory, gateway, llm, adapter, _ = runtime
    gateway.settings.team_web_enabled = True
    llm._actions.append(StructuredAction(action_type=ActionType.CREATE_PROJECT,
        understanding="创建个人项目",payload={"title":"我的学习"}))
    persist_event(sync,event("创建我的学习项目",chat_type="p2p",event_id="create"))
    assert await gateway.process_one()
    llm._actions.append(StructuredAction(action_type=ActionType.IGNORE,understanding=""))
    persist_event(sync,event("在刚才的项目里记录一项任务",chat_type="p2p",event_id="next"))
    assert await gateway.process_one()
    context=llm.calls[-1][1]
    assert [p["name"] for p in context["projects"]]==["我的学习"]
    assert any(r["action_data"]["action_type"]=="create_project" for r in context["references"])
