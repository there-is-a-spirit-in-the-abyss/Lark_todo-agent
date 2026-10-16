"""Normalize authenticated SDK events; no HTTP verification tokens here."""
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from huiyang.services.secretary import IncomingMessage


async def resolve_sender_identity(message, adapter):
    # Standard events contain IDs, not sender names. Resolve via trusted Feishu API,
    # never from message text, mention names, or a user's self-registration.
    from huiyang.adapters.feishu_api import FeishuAPIError
    profile = await adapter.get_user_profile(message.sender_id)
    if profile.user_id != message.sender_id or not profile.display_name.strip():
        raise FeishuAPIError("Invalid sender profile")
    return replace(message, sender_display_name=profile.display_name)


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    message: IncomingMessage


def normalize_event(payload, *, bot_open_id="", now=None):
    header = payload.get("header") or {}
    if header.get("event_type") != "im.message.receive_v1":
        return None
    event = payload.get("event") or {}
    sender = event.get("sender") or {}
    if sender.get("sender_type") != "user":
        return None
    body = event.get("message") or {}
    if body.get("message_type") != "text":
        return None
    ids = sender.get("sender_id") or {}
    # Never silently put an open_id into ADMIN_FEISHU_USER_ID.
    if not ids.get("user_id"):
        raise ValueError("Missing sender.user_id; enable contact:user.employee_id:readonly")
    if not header.get("event_id") or not body.get("message_id") or not body.get("chat_id"):
        raise ValueError("Missing event/message/chat ID")
    if body.get("chat_type") not in {"p2p", "group"}:
        return None
    text = json.loads(body.get("content") or "{}").get("text", "").strip()
    mentions = body.get("mentions") or []
    mentioned_bot = bool(bot_open_id) and any(
        (item.get("id") or {}).get("open_id") == bot_open_id for item in mentions
    )
    for item in mentions:
        # Retain human mentions as identity references in message content.
        key = item.get("key")
        if key:
            who = item.get("id") or {}
            replacement = ("@机器人" if who.get("open_id") == bot_open_id else
                           f"@{item.get('name', '')}[user_id={who.get('user_id', '')}]")
            text = text.replace(key, replacement)
    if not text:
        return None
    return NormalizedEvent(str(header["event_id"]), IncomingMessage(
        sender_id=str(ids["user_id"]), chat_id=str(body["chat_id"]),
        chat_type=body["chat_type"], text=text,
        received_at=(datetime.fromtimestamp(int(body["create_time"]) / 1000, UTC)
                     if body.get("create_time") else now or datetime.now(UTC)),
        message_id=str(body["message_id"]), mentioned_bot=mentioned_bot,
        sender_open_id=str(ids.get("open_id") or ""),
    ))
