from huiyang.i18n import t, language_scope
import base64
import hashlib
import re
import secrets
import time
import httpx
from contextlib import asynccontextmanager, AsyncExitStack
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update

from huiyang.adapters.feishu_api import FeishuAPIAdapter, FeishuAPIError
from huiyang.database import Database
from huiyang.team.model import apply_action, empty_board
from huiyang.team.tables import TeamOAuthState, TeamSession, TeamSpace

SESSION_COOKIE = "huiyang_team"
STATE_COOKIE = "huiyang_team_oauth"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def chat_id(value):
    if not re.fullmatch(r"oc_[A-Za-z0-9_-]{1,240}", value):
        raise HTTPException(400, t("无效的群入口"))
    return value


class Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, strict=True)
    action: dict


def setup_team(app, settings, previous_lifespan=None, dependencies=None):
    origin = settings.team_public_url.rstrip("/")
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.netloc or parsed.path
            or parsed.query or parsed.fragment or parsed.username):
        raise ValueError("TEAM_PUBLIC_URL must be a HTTPS origin")
    database = None if dependencies else Database(settings)
    sessions, adapter = dependencies or (database.session_factory,
                                        FeishuAPIAdapter(settings.feishu_app_id, settings.feishu_app_secret))
    router = APIRouter(prefix="/api/team")

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with AsyncExitStack() as stack:
                if previous_lifespan:
                    await stack.enter_async_context(previous_lifespan(application))
                yield
        finally:
            if database:
                await adapter.close()
                await database.dispose()

    async def identity(request, session):
        token = request.cookies.get(SESSION_COOKIE, "")
        found = await session.get(TeamSession, digest(token)) if token else None
        if found is None or found.expires_at <= int(time.time()):
            raise HTTPException(401, t("请通过飞书登录"))
        return found

    async def members_for(group, who):
        try:
            members = await adapter.team_members(group)
        except (FeishuAPIError, httpx.HTTPError, ValueError):
            raise HTTPException(503, t("暂时无法验证群成员身份，请稍后重试")) from None
        if who.user_id not in members:
            raise HTTPException(403, t("你不在此飞书群中，无法访问团队空间"))
        return members

    async def space_for(session, group):
        space = await session.get(TeamSpace, group)
        if space is None:
            try:
                name = await adapter.team_chat_name(group)
            except (FeishuAPIError, httpx.HTTPError, ValueError):
                raise HTTPException(503, t("暂时无法读取群信息")) from None
            dialect = session.bind.dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            await session.execute(insert(TeamSpace).values(
                chat_id=group, name=name, revision=0, board=empty_board(), people={}
            ).on_conflict_do_nothing(index_elements=["chat_id"]))
            await session.commit()
            space = await session.get(TeamSpace, group)
        return space

    def view(space, who, members):
        people = {**space.people, **members}
        for task in space.board["tasks"]:
            people.setdefault(task["owner"], t("已退群成员"))
        colors = ["#217b67", "#466aba", "#ad6b28", "#ac416a"]
        roster = [{"id": uid, "name": name, "short": name[:1], "color": colors[i % len(colors)],
                   "active": uid in members, "role": t("群成员") if uid in members else t("已退群")}
                  for i, (uid, name) in enumerate(sorted(people.items()))]
        return {"board": space.board, "revision": space.revision, "members": roster,
                "actor": who.user_id, "csrf": who.csrf, "space": {"id": space.chat_id, "name": space.name}}

    @router.get("/spaces/{group}")
    async def read_space(group: str, request: Request):
        chat_id(group)
        async with sessions() as session:
            who = await identity(request, session)
            members = await members_for(group, who)
            return view(await space_for(session, group), who, members)

    @router.post("/spaces/{group}/actions")
    async def mutate(group: str, body: Mutation, request: Request):
        chat_id(group)
        async with sessions() as session:
            who = await identity(request, session)
            if (request.headers.get("origin") != origin
                    or not secrets.compare_digest(request.headers.get("x-csrf-token", ""), who.csrf)):
                raise HTTPException(403, t("页面验证失效，请刷新"))
            members = await members_for(group, who)
            space = await space_for(session, group)
            if space.revision != body.revision:
                raise HTTPException(409, t("其他成员已更新，请刷新后重试"))
            try:
                board = apply_action(space.board, body.action, who.user_id, members)
            except PermissionError as error:
                raise HTTPException(403, str(error)) from None
            except (ValueError, TypeError, KeyError) as error:
                raise HTTPException(422, str(error)) from None
            result = await session.execute(update(TeamSpace).where(
                TeamSpace.chat_id == group, TeamSpace.revision == body.revision
            ).values(board=board, revision=body.revision+1, people={**space.people, **members})
              .execution_options(synchronize_session=False))
            if result.rowcount != 1:
                await session.rollback()
                raise HTTPException(409, t("其他成员已更新，请刷新后重试"))
            await session.commit()
            await session.refresh(space)
            return view(space, who, members)

    @router.get("/login")
    async def login(chat_id: str):
        group = globals()["chat_id"](chat_id)
        state, browser, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        now = int(time.time())
        async with sessions() as session:
            await session.execute(delete(TeamOAuthState).where(TeamOAuthState.expires_at <= now))
            await session.execute(delete(TeamSession).where(TeamSession.expires_at <= now))
            session.add(TeamOAuthState(state_hash=digest(state), browser_hash=digest(browser),
                                      chat_id=group, verifier=verifier, expires_at=now+600))
            await session.commit()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        target = "https://accounts.feishu.cn/open-apis/authen/v1/authorize?" + urlencode({
            "client_id": settings.feishu_app_id, "response_type": "code",
            "redirect_uri": origin+"/api/team/callback", "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })
        response = RedirectResponse(target, status_code=302)
        response.set_cookie(STATE_COOKIE, browser, max_age=600, secure=True,
                            httponly=True, samesite="lax", path="/api/team")
        return response

    @router.get("/callback")
    async def callback(request: Request, state: str = "", code: str = ""):
        async with sessions() as session:
            oauth = await session.get(TeamOAuthState, digest(state))
            browser = request.cookies.get(STATE_COOKIE, "")
            if (not oauth or not code or not browser or oauth.expires_at <= int(time.time())
                    or not secrets.compare_digest(oauth.browser_hash, digest(browser))):
                raise HTTPException(400, t("登录已失效，请重新打开群链接"))
            group, verifier = oauth.chat_id, oauth.verifier
            removed = await session.execute(delete(TeamOAuthState).where(
                TeamOAuthState.state_hash == digest(state)))
            await session.commit()
            if removed.rowcount != 1:
                raise HTTPException(400, t("登录凭证已使用"))
            try:
                profile = await adapter.team_oauth_identity(code, origin+"/api/team/callback", verifier)
            except (FeishuAPIError, httpx.HTTPError, ValueError):
                raise HTTPException(502, t("飞书登录未完成，请重试")) from None
            token = secrets.token_urlsafe(48)
            who = TeamSession(token_hash=digest(token), user_id=profile["open_id"],
                              display_name=profile["name"], csrf=secrets.token_urlsafe(32),
                              expires_at=int(time.time())+28800)
            await members_for(group, who)
            session.add(who)
            await session.commit()
        response = RedirectResponse("/team/"+group, status_code=302)
        response.delete_cookie(STATE_COOKIE, path="/api/team")
        response.set_cookie(SESSION_COOKIE, token, max_age=28800, secure=True,
                            httponly=True, samesite="lax", path="/api/team")
        return response

    app.include_router(router)
    static = Path(settings.team_static_dir)
    if (static / "assets").is_dir():
        app.mount("/team/assets", StaticFiles(directory=static / "assets"), name="team-assets")

    @app.get("/team")
    @app.get("/team/")
    async def team_landing():
        # Without a group the existing UI explains how to enter from Feishu.
        # Serving that UI gives installers a real public page to verify.
        if not (static / "index.html").is_file():
            raise HTTPException(503, t("团队网页尚未构建"))
        return FileResponse(static / "index.html")

    @app.get("/team/{group}")
    async def team_page(group: str):
        chat_id(group)
        if not (static / "index.html").is_file():
            raise HTTPException(503, t("团队网页尚未构建"))
        return FileResponse(static / "index.html")

    @app.middleware("http")
    async def team_headers(request, call_next):
        language = request.headers.get("accept-language", "zh-CN")
        with language_scope(language):
            response = await call_next(request)
        if request.url.path.startswith(("/api/team", "/team")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
            )
        return response
    return lifespan
