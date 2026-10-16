from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from huiyang.domain.models import Base, Task, TaskStatus, TaskVisibility
from huiyang.domain.persistence import Reminder


def load_repositories():
    try:
        return import_module("huiyang.repositories.sqlalchemy")
    except ModuleNotFoundError:
        pytest.fail("SQLAlchemy repositories are missing")


@pytest.mark.asyncio
async def test_task_and_reminder_repositories_persist_business_changes() -> None:
    repositories = load_repositories()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        tasks = repositories.SqlAlchemyTaskRepository(session)
        reminders = repositories.SqlAlchemyReminderRepository(session)
        assignee_id = uuid4()
        now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)
        task = Task(
            id=uuid4(),
            title="完成首页",
            original_instruction="完成首页",
            creator_id=uuid4(),
            assignee_id=assignee_id,
            visibility=TaskVisibility.TEAM,
            status=TaskStatus.TODO,
        )

        await tasks.add(task)
        active = await tasks.list_active_by_assignee(assignee_id)
        assert active == [task]

        reminder = Reminder(
            id=uuid4(),
            task_id=task.id,
            scheduled_for=now + timedelta(hours=1),
            kind="default",
            destination="group",
            destination_chat_id="oc_group",
        )
        await reminders.add_many([reminder])
        await reminders.cancel_pending(task.id, canceled_at=now)
        assert reminder.canceled_at == now

        task.set_status(TaskStatus.COMPLETED, now=now)
        await tasks.save(task)
        assert await tasks.list_active_by_assignee(assignee_id) == []

    await engine.dispose()
