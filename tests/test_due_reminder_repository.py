from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from huiyang.domain.models import Base, Task, TaskStatus, TaskVisibility
from huiyang.domain.persistence import Reminder, User
from huiyang.repositories.sqlalchemy import SqlAlchemyDueReminderRepository


@pytest.mark.asyncio
async def test_due_reminder_repository_joins_task_and_assignee_and_marks_sent() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)

    async with factory() as session:
        user = User(
            id=uuid4(),
            feishu_user_id="ou_xiao",
            display_name="小王",
        )
        task = Task(
            id=uuid4(),
            title="完成首页",
            original_instruction="完成首页",
            creator_id=user.id,
            assignee_id=user.id,
            visibility=TaskVisibility.TEAM,
            source_chat_id="oc_group",
            status=TaskStatus.TODO,
            deadline=now,
        )
        due = Reminder(
            id=uuid4(),
            task_id=task.id,
            scheduled_for=now,
            kind="default",
            destination="group",
            destination_chat_id="oc_group",
        )
        future = Reminder(
            id=uuid4(),
            task_id=task.id,
            scheduled_for=now + timedelta(hours=1),
            kind="default",
            destination="group",
            destination_chat_id="oc_group",
        )
        session.add_all([user, task, due, future])
        await session.flush()

        repository = SqlAlchemyDueReminderRepository(session)
        deliveries = await repository.due(now)

        assert len(deliveries) == 1
        assert deliveries[0].reminder_id == str(due.id)
        assert deliveries[0].assignee_user_id == "ou_xiao"
        assert deliveries[0].chat_id == "oc_group"
        assert deliveries[0].text == "「完成首页」已到截止时间"

        await repository.mark_triggered(
            deliveries[0].reminder_id,
            triggered_at=now,
        )
        assert due.triggered_at == now
        assert await repository.due(now) == []

    await engine.dispose()
