from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from huiyang.domain.models import Base
from huiyang.domain.persistence import ConversationMemory


@pytest.mark.asyncio
async def test_memory_retrieval_keeps_live_personal_and_project_references() -> None:
    try:
        repository_module = import_module("huiyang.repositories.memory")
    except ModuleNotFoundError:
        pytest.fail("Conversation Memory repository is missing")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)
    first_task, second_task = uuid4(), uuid4()

    async with factory() as session:
        repository = repository_module.SqlAlchemyMemoryRepository(session)
        await repository.add(
            ConversationMemory(
                id=uuid4(),
                chat_id="oc_group",
                sender_id="ou_xiao",
                raw_message="给我看任务",
                action_data={"type": "list_tasks"},
                resolved_task_ids=[str(first_task), str(second_task)],
                result_data={"shown": 2},
                scope="personal",
                expires_at=now + timedelta(days=7),
                created_at=now,
            )
        )
        await repository.add(
            ConversationMemory(
                id=uuid4(),
                chat_id="oc_group",
                sender_id="ou_xiao",
                raw_message="旧任务",
                resolved_task_ids=["expired"],
                scope="personal",
                expires_at=now - timedelta(seconds=1),
                created_at=now - timedelta(days=8),
            )
        )
        await repository.add(
            ConversationMemory(
                id=uuid4(),
                chat_id="oc_group",
                sender_id="ou_xiao",
                raw_message="项目任务",
                resolved_task_ids=["project-task"],
                scope="project",
                expires_at=None,
                created_at=now - timedelta(days=30),
            )
        )

        memories = await repository.relevant(
            chat_id="oc_group",
            sender_id="ou_xiao",
            now=now,
        )

    assert [memory.raw_message for memory in memories] == ["给我看任务", "项目任务"]
    assert memories[0].resolved_task_ids[1] == str(second_task)
    await engine.dispose()
