import json

import httpx
import pytest

from huiyang.adapters.feishu_api import FeishuAPIAdapter, FeishuAPIError


@pytest.mark.asyncio
async def test_membership_paginates_and_does_not_use_bot_identity_as_user():
    pages = []
    def handle(req):
        if "tenant_access_token" in req.url.path:
            return httpx.Response(200, json={"code":0,"tenant_access_token":"bot","expire":7200})
        assert req.url.params["member_id_type"] == "open_id"
        page = req.url.params.get("page_token", "")
        pages.append(page)
        return httpx.Response(200, json={"code":0,"data":{
            "items":[{"member_id":"b" if page else "a","member_id_type":"open_id","name":"User"}],
            "has_more":not bool(page),"page_token":"" if page else "next"}})
    adapter = FeishuAPIAdapter("app","secret",client=httpx.AsyncClient(
        base_url="https://open.feishu.cn",transport=httpx.MockTransport(handle)))
    try:
        assert set(await adapter.team_members("oc_test")) == {"a","b"}
        assert pages == ["","next"]
    finally:
        await adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    {"items":[]}, {"items":[],"has_more":True,"page_token":""},
    {"items":[{"member_id":"u","member_id_type":"user_id"}],"has_more":False},
])
async def test_incomplete_roster_never_opens_departed_owner_permissions(data):
    def handle(req):
        if "tenant_access_token" in req.url.path:
            return httpx.Response(200,json={"code":0,"tenant_access_token":"bot","expire":7200})
        return httpx.Response(200,json={"code":0,"data":data})
    adapter=FeishuAPIAdapter("app","secret",client=httpx.AsyncClient(
        base_url="https://open.feishu.cn",transport=httpx.MockTransport(handle)))
    try:
        with pytest.raises(FeishuAPIError):
            await adapter.team_members("oc_test")
    finally: await adapter.close()


@pytest.mark.asyncio
async def test_oauth_exchanges_code_with_pkce_and_reads_verified_profile():
    calls=[]
    def handle(req):
        calls.append(req)
        if req.url.path.endswith("/oauth/token"):
            body=json.loads(req.content)
            assert body["code_verifier"]=="verifier"
            assert body["redirect_uri"]=="https://team.test/api/team/callback"
            return httpx.Response(200,json={"code":0,"access_token":"user-token"})
        assert req.headers["authorization"]=="Bearer user-token"
        return httpx.Response(200,json={"code":0,"data":{"open_id":"a","name":"甲"}})
    adapter=FeishuAPIAdapter("app","secret",client=httpx.AsyncClient(
        base_url="https://open.feishu.cn",transport=httpx.MockTransport(handle)))
    try:
        profile=await adapter.team_oauth_identity("code","https://team.test/api/team/callback","verifier")
        assert profile["open_id"]=="a"
        assert len(calls)==2
    finally: await adapter.close()
