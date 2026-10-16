from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from huiyang.adapters.feishu import FeishuAdapter


@dataclass(frozen=True, slots=True)
class ReminderDelivery:
    reminder_id: str
    destination: str
    assignee_user_id: str
    chat_id: str | None
    text: str


class DueReminderRepository(Protocol):
    async def due(self, now: datetime) -> list[ReminderDelivery]: ...
    async def mark_triggered(
        self,
        reminder_id: str,
        *,
        triggered_at: datetime,
    ) -> None: ...


class ReminderProcessor:
    def __init__(
        self,
        repository: DueReminderRepository,
        feishu: FeishuAdapter,
    ) -> None:
        self._repository = repository
        self._feishu = feishu

    async def deliver_due(self, now: datetime) -> int:
        deliveries = await self._repository.due(now)
        for delivery in deliveries:
            if delivery.destination == "private":
                await self._feishu.send_private(
                    delivery.assignee_user_id,
                    delivery.text,
                )
            else:
                if delivery.chat_id is None:
                    raise ValueError("Group reminder requires chat_id")
                await self._feishu.send_group(
                    delivery.chat_id,
                    delivery.text,
                    mention_user_id=delivery.assignee_user_id,
                )
            await self._repository.mark_triggered(
                delivery.reminder_id,
                triggered_at=now,
            )
        return len(deliveries)
