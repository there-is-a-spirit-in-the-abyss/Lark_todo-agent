from importlib import import_module

import pytest

from huiyang.config import Settings


@pytest.mark.asyncio
async def test_database_builds_async_engine_from_settings() -> None:
    try:
        database_module = import_module("huiyang.database")
    except ModuleNotFoundError:
        pytest.fail("database factory is missing")

    database = database_module.Database(
        Settings(database_url="sqlite+aiosqlite:///:memory:", _env_file=None)
    )

    assert database.engine.url.drivername == "sqlite+aiosqlite"
    assert database.engine.url.database == ":memory:"
    assert database.session_factory.kw["expire_on_commit"] is False
    await database.dispose()
