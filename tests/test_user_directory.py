from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from huiyang.domain.models import Base
from huiyang.domain.persistence import User
from huiyang.repositories.sqlalchemy import SqlAlchemyUserDirectory


@pytest.mark.asyncio
async def test_user_directory_resolves_internal_and_feishu_ids() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user = User(
        id=uuid4(),
        feishu_user_id="ou_xiao",
        display_name="小王",
    )

    async with factory() as session:
        session.add(user)
        await session.flush()
        directory = SqlAlchemyUserDirectory(session)

        by_feishu = await directory.by_feishu_id("ou_xiao")
        by_id = await directory.by_id(user.id)

        assert by_feishu == by_id
        assert by_id is not None
        assert by_id.id == user.id
        assert by_id.display_name == "小王"

    await engine.dispose()
