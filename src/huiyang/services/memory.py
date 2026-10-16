from __future__ import annotations

from datetime import timedelta
from typing import Any, Protocol
from uuid import uuid4

from huiyang.domain.persistence import ConversationMemory
from huiyang.services.secretary import (
    IncomingMessage,
    SecretaryResponse,
)


class SecretaryHandler(Protocol):
    async def handle(
        self,
        message: IncomingMessage,
        *,
        context: dict[str, Any],
    ) -> SecretaryResponse: ...


class MemoryRepository(Protocol):
    async def relevant(
        self,
        *,
        chat_id: str,
        sender_id: str,
        now: object,
    ) -> list[ConversationMemory]: ...

    async def add(self, memory: ConversationMemory) -> ConversationMemory: ...


class MemoryAwareSecretary:
    def __init__(
        self,
        *,
        delegate: SecretaryHandler,
        memories: MemoryRepository,
    ) -> None:
        self._delegate = delegate
        self._memories = memories

    async def handle(
        self,
        message: IncomingMessage,
        *,
        context: dict[str, Any],
    ) -> SecretaryResponse:
        references = await self._memories.relevant(
            chat_id=message.chat_id,
            sender_id=message.sender_id,
            now=message.received_at,
        )
        enriched = dict(context)
        enriched["references"] = [
            {
                "raw_message": item.raw_message,
                "action_data": item.action_data,
                "resolved_task_ids": item.resolved_task_ids,
                "resolved_project_id": (
                    str(item.resolved_project_id)
                    if item.resolved_project_id is not None
                    else None
                ),
                "result_data": item.result_data,
                "scope": item.scope,
            }
            for item in references
        ]
        response = await self._delegate.handle(message, context=enriched)
        action = response.action
        if action.action_type.value == "ignore":
            return response
        project_scope = action.project_id is not None
        await self._memories.add(
            ConversationMemory(
                id=uuid4(),
                chat_id=message.chat_id,
                sender_id=message.sender_id,
                raw_message=message.text,
                action_data=action.model_dump(mode="json"),
                resolved_task_ids=(
                    response.resolved_task_ids or
                    ([str(action.task_id)] if action.task_id is not None else [])
                ),
                resolved_project_id=action.project_id,
                result_data={"response_text": response.text},
                scope="project" if project_scope else "personal",
                expires_at=(
                    None
                    if project_scope
                    else message.received_at + timedelta(days=7)
                ),
                created_at=message.received_at,
            )
        )
        return response
