"""Opt-in against project PostgreSQL; every run uses an isolated temporary schema."""
import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from huiyang.config import Settings
from huiyang.domain.models import Base
from huiyang.domain.persistence import AdminBinding
from huiyang.services.enrollment import bind_group_admin_if_unset, effective_admin
from huiyang.services.permissions import PermissionService
from huiyang.services.secretary import IncomingMessage


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("RUN_POSTGRES_IDENTITY_TESTS") != "1", reason="Requires project PostgreSQL")
async def test_postgres_concurrent_first_senders_cannot_replace_singleton():
    url = Settings().database_url
    assert url.startswith("postgresql+asyncpg://")
    schema = "huiyang_identity_test_" + uuid4().hex
    owner = create_async_engine(url)
    engine = None
    try:
        async with owner.begin() as connection:
            await connection.execute(CreateSchema(schema))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async def discover(uid):
            async def get_chat_owner(chat_id):
                return SimpleNamespace(chat_id=chat_id, user_id=uid)
            adapter = SimpleNamespace(get_chat_owner=get_chat_owner)
            async with factory() as session:
                message = IncomingMessage("u_member", "test", "group", "普通消息", datetime.now(UTC))
                await bind_group_admin_if_unset(session, message, adapter)
                await session.commit()
                return await effective_admin(session)
        winners = await asyncio.gather(discover("u_first"), discover("u_second"))
        assert len(set(winners)) == 1
        winner = winners[0]
        assert winner in {"u_first", "u_second"}
        async with factory() as session:
            assert await session.scalar(select(func.count(AdminBinding.singleton))) == 1
            service = PermissionService(await effective_admin(session))
            assert sum(service.is_admin(uid) for uid in ["u_first", "u_second"]) == 1
            # Later owner changes must not even trigger another API lookup.
            async def forbidden(chat_id):
                raise AssertionError("Do not query group ownership once bound")
            await bind_group_admin_if_unset(session,
                IncomingMessage("u_third", "test", "group", "消息", datetime.now(UTC)),
                SimpleNamespace(get_chat_owner=forbidden))
            await session.commit()
            assert await effective_admin(session) == winner
    finally:
        if engine is not None:
            await engine.dispose()
        assert schema.startswith("huiyang_identity_test_") and len(schema.split("_")[-1]) == 32
        async with owner.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        await owner.dispose()
