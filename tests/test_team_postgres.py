import asyncio
import hashlib
import os
import time
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from huiyang.config import Settings
from huiyang.domain.models import Base
from huiyang.main import create_app
from huiyang.team.tables import TeamSession, TeamSpace
from test_team_api import Feishu


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("RUN_POSTGRES_TEAM_TESTS") != "1", reason="Requires project PostgreSQL")
async def test_postgres_first_load_and_simultaneous_mutations_are_atomic():
    owner = create_async_engine(Settings().database_url)
    schema = "huiyang_team_test_" + uuid4().hex
    engine = None
    try:
        async with owner.begin() as conn:
            await conn.execute(CreateSchema(schema))
        engine = create_async_engine(Settings().database_url,
            connect_args={"server_settings":{"search_path":schema}})
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as s:
            s.add(TeamSession(token_hash=hashlib.sha256(b"test").hexdigest(),user_id="a",
                display_name="A",csrf="csrf",expires_at=int(time.time())+3600))
            await s.commit()
        settings = Settings(_env_file=None, platform_enabled=False, team_web_enabled=True,
                            team_public_url="https://team.test")
        app = create_app(settings=settings,team_dependencies=(sessions,Feishu()))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="https://team.test",
            cookies={"huiyang_team":"test"},headers={"Origin":"https://team.test","X-CSRF-Token":"csrf"}) as c:
            reads = await asyncio.gather(c.get("/api/team/spaces/oc_test"),c.get("/api/team/spaces/oc_test"))
            assert all(r.status_code==200 for r in reads)
            async def write(name):
                return await c.post("/api/team/spaces/oc_test/actions",json={
                    "revision":0,"action":{"type":"createProject","id":str(uuid4()),"name":name}})
            responses = await asyncio.gather(write("one"),write("two"))
            assert sorted(r.status_code for r in responses)==[200,409]
            state=(await c.get("/api/team/spaces/oc_test")).json()
            assert state["revision"]==1 and len(state["board"]["projects"])==1
        async with sessions() as s:
            assert len(list(await s.scalars(select(TeamSpace))))==1
    finally:
        if engine: await engine.dispose()
        assert schema.startswith("huiyang_team_test_") and len(schema.rsplit("_",1)[1])==32
        async with owner.begin() as conn:
            await conn.execute(DropSchema(schema,cascade=True,if_exists=True))
        await owner.dispose()
