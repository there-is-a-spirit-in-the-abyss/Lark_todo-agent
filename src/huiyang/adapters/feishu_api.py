"""Feishu outbound API; accepts real user_id, never display names."""
import asyncio
import html
import json
import time
from contextvars import ContextVar
from uuid import NAMESPACE_URL, uuid5
from urllib.parse import quote
from huiyang.adapters.feishu import FeishuUserProfile, FeishuChatOwner
from huiyang.team.feishu import TeamFeishuMixin
from huiyang.adapters.errors import FeishuAPIError

import httpx

delivery_key = ContextVar("delivery_key", default="")


class FeishuAPIAdapter(TeamFeishuMixin):
    def __init__(self, app_id, app_secret, *, client=None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = client or httpx.AsyncClient(
            base_url="https://open.feishu.cn", timeout=15,
        )
        self._token = ""
        self._expires_at = 0
        self._lock = asyncio.Lock()

    async def _access_token(self):
        async with self._lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token
            response = await self.client.post(
                "/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            data = self._check(response)
            self._token = data["tenant_access_token"]
            self._expires_at = time.monotonic() + max(0, data["expire"] - 60)
            return self._token

    @staticmethod
    def _check(response):
        if response.status_code != 200:
            raise FeishuAPIError(f"Feishu HTTP {response.status_code}")
        data = response.json()
        if data.get("code") != 0:
            raise FeishuAPIError(f"Feishu code {data.get('code', 'missing')}")
        return data

    async def request(self, method, path, **kwargs):
        for attempt in range(2):
            token = await self._access_token()
            response = await self.client.request(
                method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs,
            )
            if response.status_code == 200 and response.json().get("code") in (99991663, 99991668):
                self._token = ""
                if attempt == 0:
                    continue
            return self._check(response)
        raise FeishuAPIError("Feishu token renewal failed")

    async def bot_open_id(self):
        result = await self.request("GET", "/open-apis/bot/v3/info")
        return result["bot"]["open_id"]

    async def get_chat_owner(self, chat_id):
        if not isinstance(chat_id, str) or not chat_id.strip():
            raise FeishuAPIError("Missing group chat ID")
        result = await self.request(
            "GET", "/open-apis/im/v1/chats/" + quote(chat_id, safe=""),
            params={"user_id_type": "user_id"},
        )
        data = result.get("data") or {}
        owner_id = data.get("owner_id")
        if data.get("chat_mode") not in {"group", "topic"}:
            raise FeishuAPIError("Expected group chat information")
        if data.get("owner_id_type") != "user_id":
            raise FeishuAPIError("Group owner must use user_id; require contact:user.employee_id:readonly")
        if not isinstance(owner_id, str) or not owner_id.strip() or len(owner_id) > 255:
            raise FeishuAPIError("Group has no valid human owner ID")
        return FeishuChatOwner(chat_id, owner_id)

    async def get_user_profile(self, user_id):
        result = await self.request(
            "GET", "/open-apis/contact/v3/users/" + quote(user_id, safe=""),
            params={"user_id_type": "user_id"},
        )
        user = (result.get("data") or {}).get("user") or {}
        name = user.get("name")
        if user.get("user_id") != user_id:
            raise FeishuAPIError("Sender profile ID mismatch")
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise FeishuAPIError("Missing sender name; require contact:user.base:readonly")
        return FeishuUserProfile(user_id, name)

    async def _send(self, kind, target, text):
        body = {"receive_id": target, "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False)}
        if delivery_key.get():
            body["uuid"] = str(uuid5(NAMESPACE_URL, delivery_key.get() + ":" + target))
        await self.request(
            "POST", "/open-apis/im/v1/messages",
            params={"receive_id_type": kind}, json=body,
        )

    async def send_private(self, user_id, text):
        await self._send("user_id", user_id, text)

    async def send_group(self, chat_id, text, *, mention_user_id=None):
        if mention_user_id:
            text = f'<at user_id="{html.escape(mention_user_id, quote=True)}">负责人</at> ' + text
        await self._send("chat_id", chat_id, text)

    async def close(self):
        await self.client.aclose()
