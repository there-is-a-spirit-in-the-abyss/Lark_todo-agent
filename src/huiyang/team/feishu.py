from huiyang.i18n import t
from urllib.parse import quote

from huiyang.adapters.errors import FeishuAPIError


class TeamFeishuMixin:
    async def team_chat_name(self, chat_id):
        result = await self.request("GET", "/open-apis/im/v1/chats/" + quote(chat_id, safe=""))
        data = result.get("data") or {}
        if data.get("chat_mode") not in ("group", "topic"):
            raise FeishuAPIError("Expected a group")
        return data.get("name") or t("团队空间")

    async def team_members(self, chat_id):
        members, seen, page = {}, set(), ""
        while True:
            params = {"member_id_type": "open_id", "page_size": 100}
            if page:
                params["page_token"] = page
            result = await self.request("GET", "/open-apis/im/v1/chats/" + quote(chat_id, safe="") + "/members",
                                        params=params)
            data = result.get("data") or {}
            if not isinstance(data.get("items"), list) or not isinstance(data.get("has_more"), bool):
                raise FeishuAPIError("Incomplete membership response")
            for person in data["items"]:
                uid = person.get("member_id")
                if not isinstance(uid, str) or not uid or person.get("member_id_type") != "open_id":
                    raise FeishuAPIError("Invalid member identity")
                members[uid] = person.get("name") or t("群成员")
            if not data["has_more"]:
                return members
            page = data.get("page_token")
            if not page or page in seen or len(seen) > 1000:
                raise FeishuAPIError("Invalid membership pagination")
            seen.add(page)

    async def team_oauth_identity(self, code, redirect_uri, verifier):
        response = await self.client.post("/open-apis/authen/v2/oauth/token", json={
            "grant_type": "authorization_code", "client_id": self.app_id,
            "client_secret": self.app_secret, "code": code,
            "redirect_uri": redirect_uri, "code_verifier": verifier,
        })
        if response.status_code != 200:
            raise FeishuAPIError("OAuth exchange failed")
        data = response.json()
        token = data.get("access_token")
        if not token or data.get("error") or data.get("code", 0) != 0:
            raise FeishuAPIError("OAuth exchange rejected")
        response = await self.client.get("/open-apis/authen/v1/user_info",
                                          headers={"Authorization": "Bearer " + token})
        profile = self._check(response).get("data") or {}
        if not profile.get("open_id") or not profile.get("name"):
            raise FeishuAPIError("OAuth identity missing")
        return profile
