import hashlib
import time
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from huiyang.config import Settings
from huiyang.domain.models import Base
from huiyang.main import create_app
from huiyang.team.tables import TeamSession, TeamOAuthState


class Feishu:
    def __init__(self):
        self.people = {"a": "甲", "b": "乙"}
        self.fail = False

    async def team_members(self, chat_id):
        if self.fail:
            from huiyang.adapters.feishu_api import FeishuAPIError
            raise FeishuAPIError("unavailable")
        return dict(self.people) if chat_id == "oc_test" else {}

    async def team_chat_name(self, chat_id):
        return "测试团队"

    async def team_oauth_identity(self, code, redirect_uri, verifier):
        return {"open_id": "a", "name": "甲"}


@pytest_asyncio.fixture
async def web(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "web.sqlite"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    api = Feishu()
    settings = Settings(_env_file=None, team_web_enabled=True, team_public_url="https://team.test",
                        feishu_app_id="app", feishu_app_secret="secret")
    app = create_app(settings=settings, team_dependencies=(sessions, api))
    async with sessions() as s:
        s.add(TeamSession(token_hash=hashlib.sha256(b"session").hexdigest(), user_id="a",
                          display_name="甲", csrf="csrf", expires_at=int(time.time())+3600))
        await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://team.test",
                                cookies={"huiyang_team": "session"}) as client:
        yield client, api, sessions
    await engine.dispose()


@pytest.mark.asyncio
async def test_auth_membership_csrf_conflict_and_isolated_spaces(web):
    client, api, _ = web
    url = "/api/team/spaces/oc_test"
    first = await client.get(url)
    assert first.status_code == 200, first.text
    assert first.json()["board"]["tasks"] == []
    action = {"revision": 0, "action": {"type": "createProject", "id": "c6abf71e-8a9e-4f33-9d15-7dd78960c702", "name": "项目"}}
    assert (await client.post(url + "/actions", json=action)).status_code == 403
    headers = {"X-CSRF-Token": "csrf", "Origin": "https://team.test"}
    assert (await client.post(url + "/actions", json=action, headers=headers)).status_code == 200
    assert (await client.post(url + "/actions", json=action, headers=headers)).status_code == 409
    assert (await client.get("/api/team/spaces/oc_other")).status_code == 403
    api.people.pop("a")
    assert (await client.get(url)).status_code == 403
    assert (await client.post(url + "/actions", json=action, headers=headers)).status_code == 403
    api.fail = True
    assert (await client.get(url)).status_code == 503
    client.cookies.clear()
    assert (await client.get(url)).status_code == 401


@pytest.mark.asyncio
async def test_oauth_is_browser_bound_single_use_and_does_not_trust_user_id(web):
    client, api, sessions = web
    from urllib.parse import urlparse, parse_qs
    response = await client.get("/api/team/login?chat_id=oc_test")
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    response = await client.get("/api/team/callback", params={"state": state, "code": "valid"})
    assert response.status_code == 302
    assert response.headers["location"] == "/team/oc_test"
    assert (await client.get("/api/team/callback", params={"state": state, "code": "valid"})).status_code == 400
    async with sessions() as s:
        assert await s.scalar(select(TeamOAuthState)) is None


@pytest.mark.asyncio
async def test_invalid_origin_and_bad_action_fail_without_mutation(web):
    client, _, _ = web
    url = "/api/team/spaces/oc_test"
    data = {"revision": 0, "action": {"type": "createProject", "id": "c6abf71e-8a9e-4f33-9d15-7dd78960c702", "name": "项目"}}
    bad = {"X-CSRF-Token": "csrf", "Origin": "https://evil.test"}
    assert (await client.post(url+"/actions", json=data, headers=bad)).status_code == 403
    good = {"X-CSRF-Token": "csrf", "Origin": "https://team.test"}
    data["action"]["owner"] = "b"
    assert (await client.post(url+"/actions", json=data, headers=good)).status_code == 422
    assert (await client.get(url)).json()["revision"] == 0


@pytest.mark.asyncio
async def test_network_outage_fails_closed_with_service_error(web):
    client, api, _ = web
    async def unavailable(group):
        raise httpx.ConnectError("offline")
    api.team_members = unavailable
    assert (await client.get("/api/team/spaces/oc_test")).status_code == 503


@pytest.mark.asyncio
async def test_callback_from_other_browser_does_not_consume_legitimate_state(web):
    from urllib.parse import urlparse, parse_qs
    client, _, _ = web
    response=await client.get("/api/team/login?chat_id=oc_test")
    state=parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    browser=client.cookies.get("huiyang_team_oauth")
    client.cookies.clear()
    assert (await client.get("/api/team/callback",params={"state":state,"code":"ok"})).status_code==400
    client.cookies.set("huiyang_team_oauth",browser)
    assert (await client.get("/api/team/callback",params={"state":state,"code":"ok"})).status_code==302


@pytest.mark.asyncio
async def test_error_language_uses_request_preference_and_keeps_auth_required(web):
    client,_,_=web
    client.cookies.clear()
    english=await client.get('/api/team/spaces/oc_test',headers={'Accept-Language':'en-US'})
    assert english.status_code==401
    assert english.json()['detail']=='Please sign in with Feishu'
    chinese=await client.get('/api/team/spaces/oc_test')
    assert chinese.status_code==401
    assert chinese.json()['detail']=='请通过飞书登录'


@pytest.mark.asyncio
async def test_installer_landing_serves_the_real_frontend_without_creating_group_data(web, tmp_path):
    client, api, sessions = web
    from sqlalchemy import func
    from huiyang.team.tables import TeamSpace
    static = tmp_path / 'static'
    static.mkdir()
    (static / 'index.html').write_text('<!doctype html><div id="root">team frontend</div>', encoding='utf-8')
    settings = Settings(_env_file=None, team_web_enabled=True, team_public_url='https://team.test',
                        feishu_app_id='app', feishu_app_secret='secret', team_static_dir=str(static))
    app = create_app(settings=settings, team_dependencies=(sessions, api))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://team.test') as visitor:
        for path in ('/team', '/team/'):
            page = await visitor.get(path)
            assert page.status_code == 200
            assert 'team frontend' in page.text
            assert page.headers['cache-control'] == 'no-store'
        assert (await visitor.get('/api/team/spaces/oc_test')).status_code == 401
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(TeamSpace)) == 0
