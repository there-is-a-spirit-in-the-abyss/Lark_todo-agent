from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FeishuUserProfile:
    user_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class FeishuChatOwner:
    chat_id: str
    user_id: str


class FeishuAdapter(Protocol):
    async def get_chat_owner(self, chat_id: str) -> FeishuChatOwner: ...
    async def get_user_profile(self, user_id: str) -> FeishuUserProfile: ...
    async def send_private(self, user_id: str, text: str) -> None: ...
    async def send_group(
        self,
        chat_id: str,
        text: str,
        *,
        mention_user_id: str | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class SentMessage:
    channel: str
    target_id: str
    text: str
    mention_user_id: str | None


class MockFeishuAdapter:
    def __init__(self) -> None:
        self.messages: list[SentMessage] = []
        self.profiles: dict[str, str] = {}
        self.chat_owners: dict[str, str] = {}

    async def get_chat_owner(self, chat_id: str) -> FeishuChatOwner:
        return FeishuChatOwner(chat_id, self.chat_owners[chat_id])

    async def get_user_profile(self, user_id: str) -> FeishuUserProfile:
        return FeishuUserProfile(user_id, self.profiles.get(user_id, user_id))

    async def send_private(self, user_id: str, text: str) -> None:
        self.messages.append(
            SentMessage(
                channel="private",
                target_id=user_id,
                text=text,
                mention_user_id=None,
            )
        )

    async def send_group(
        self,
        chat_id: str,
        text: str,
        *,
        mention_user_id: str | None = None,
    ) -> None:
        self.messages.append(
            SentMessage(
                channel="group",
                target_id=chat_id,
                text=text,
                mention_user_id=mention_user_id,
            )
        )
