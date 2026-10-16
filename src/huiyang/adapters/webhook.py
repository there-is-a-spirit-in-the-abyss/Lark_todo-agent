from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from huiyang.adapters.feishu import FeishuAdapter
from huiyang.services.secretary import IncomingMessage, SecretaryResponse


class SecretaryHandler(Protocol):
    async def handle(
        self,
        message: IncomingMessage,
        *,
        context: dict[str, Any],
    ) -> SecretaryResponse: ...


class FeishuWebhookGateway:
    """Normalize Feishu callbacks before they enter the Secretary Agent."""

    def __init__(
        self,
        *,
        verification_token: str,
        agent: SecretaryHandler,
        adapter: FeishuAdapter,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._verification_token = verification_token
        self._agent = agent
        self._adapter = adapter
        self._now = now or (lambda: datetime.now(UTC))
        self._processed_event_ids: set[str] = set()

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_token(payload)
        if payload.get("type") == "url_verification":
            return {"challenge": str(payload.get("challenge", ""))}

        header = payload.get("header") or {}
        if header.get("event_type") != "im.message.receive_v1":
            return {"code": 0}

        event_id = str(header.get("event_id", ""))
        if event_id and event_id in self._processed_event_ids:
            return {"code": 0}

        message_data = (payload.get("event") or {}).get("message") or {}
        if message_data.get("message_type") != "text":
            return {"code": 0}

        sender = (payload.get("event") or {}).get("sender") or {}
        sender_ids = sender.get("sender_id") or {}
        sender_id = str(sender_ids.get("open_id") or sender_ids.get("user_id") or "")
        chat_id = str(message_data.get("chat_id", ""))
        chat_type = str(message_data.get("chat_type", ""))
        content = json.loads(message_data.get("content") or "{}")
        text = str(content.get("text", "")).strip()
        if not sender_id or not chat_id or not text:
            raise ValueError("Feishu text event is missing sender, chat, or text")

        message = IncomingMessage(
            sender_id=sender_id,
            chat_id=chat_id,
            chat_type=chat_type,
            text=text,
            received_at=self._now(),
        )
        response = await self._agent.handle(message, context={})
        if chat_type == "p2p":
            await self._adapter.send_private(sender_id, response.text)
        else:
            await self._adapter.send_group(chat_id, response.text)

        if event_id:
            self._processed_event_ids.add(event_id)
        return {"code": 0}

    def _assert_token(self, payload: dict[str, Any]) -> None:
        if not self._verification_token:
            return
        header = payload.get("header") or {}
        actual = payload.get("token") or header.get("token")
        if actual != self._verification_token:
            raise PermissionError("Invalid Feishu verification token")
