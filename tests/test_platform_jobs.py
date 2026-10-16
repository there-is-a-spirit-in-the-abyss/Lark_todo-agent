import pytest
from sqlalchemy import select

from huiyang.adapters.long_connection import persist_event
from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.domain.persistence import Project, Reminder
from huiyang.services.background import BackgroundJobs
from test_live_gateway import runtime
from test_platform_adapters import event


@pytest.mark.asyncio
async def test_project_creation_does_not_invent_admin_only_rule(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    llm._actions.append(StructuredAction(action_type=ActionType.CREATE_PROJECT,
        understanding="建立联调项目", payload={"title": "联调项目"}))
    persist_event(sync, event("建立联调项目", chat_type="p2p"))
    assert await gateway.process_one()
    async with factory() as session:
        assert await session.scalar(select(Project.name)) == "联调项目"


@pytest.mark.asyncio
async def test_weekly_summary_is_delivered_once_and_unbound_project_is_skipped(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    async with factory() as session:
        session.add_all([Project(name="已配置", summary_chat_id="oc_target"),
                         Project(name="未配置")])
        await session.commit()
    jobs = BackgroundJobs(factory, adapter, gateway.settings)
    await jobs.weekly_summary()
    await jobs.weekly_summary()
    assert len(adapter.messages) == 1
    assert "已配置" in adapter.messages[0].text


@pytest.mark.asyncio
async def test_due_private_reminder_is_persisted_and_not_sent_twice(runtime):
    sync, factory, gateway, llm, adapter, env = runtime
    llm._actions.append(StructuredAction(action_type=ActionType.CREATE_TASK,
        understanding="记录任务", payload={"title": "联调", "visibility": "personal",
        "deadline": "2020-01-01T00:00:00+00:00"}))
    persist_event(sync, event("记录任务", chat_type="p2p"))
    assert await gateway.process_one()
    adapter.messages.clear()
    jobs = BackgroundJobs(factory, adapter, gateway.settings)
    await jobs.reminders()
    first_count = len(adapter.messages)
    assert first_count > 0
    await jobs.reminders()
    assert len(adapter.messages) == first_count
    async with factory() as session:
        reminders = list(await session.scalars(select(Reminder)))
        assert all(item.triggered_at is not None for item in reminders)
