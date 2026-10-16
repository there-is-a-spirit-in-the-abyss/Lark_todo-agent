from datetime import UTC, datetime
from importlib import import_module

import pytest


def load_modules():
    try:
        feishu = import_module("huiyang.adapters.feishu")
        reminders = import_module("huiyang.services.reminders")
        return feishu, reminders
    except ModuleNotFoundError:
        pytest.fail("Feishu reminder modules are missing")


class FakeDueRepository:
    def __init__(self, deliveries) -> None:
        self.deliveries = deliveries
        self.triggered = []

    async def due(self, now):
        return self.deliveries

    async def mark_triggered(self, reminder_id, *, triggered_at):
        self.triggered.append((reminder_id, triggered_at))


@pytest.mark.asyncio
async def test_reminders_route_personal_to_dm_and_team_to_source_group() -> None:
    feishu, reminders = load_modules()
    now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)
    repository = FakeDueRepository(
        [
            reminders.ReminderDelivery(
                reminder_id="r1",
                destination="private",
                assignee_user_id="ou_xiao",
                chat_id=None,
                text="「整理文档」将在 1 小时后截止",
            ),
            reminders.ReminderDelivery(
                reminder_id="r2",
                destination="group",
                assignee_user_id="ou_xiao",
                chat_id="oc_group",
                text="「完成首页」已到截止时间",
            ),
        ]
    )
    adapter = feishu.MockFeishuAdapter()
    processor = reminders.ReminderProcessor(repository, adapter)

    count = await processor.deliver_due(now)

    assert count == 2
    assert adapter.messages == [
        feishu.SentMessage(
            channel="private",
            target_id="ou_xiao",
            text="「整理文档」将在 1 小时后截止",
            mention_user_id=None,
        ),
        feishu.SentMessage(
            channel="group",
            target_id="oc_group",
            text="「完成首页」已到截止时间",
            mention_user_id="ou_xiao",
        ),
    ]
    assert repository.triggered == [("r1", now), ("r2", now)]
