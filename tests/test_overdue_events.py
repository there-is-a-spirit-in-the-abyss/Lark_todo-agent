from datetime import UTC, datetime, timedelta
from uuid import uuid4

from huiyang.domain.models import Task, TaskStatus, TaskVisibility
from huiyang.services.overdue import collect_overdue_events


def test_overdue_events_are_derived_without_sending_notifications() -> None:
    now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)
    assignee_id = uuid4()
    overdue = Task(
        id=uuid4(),
        title="已经逾期",
        original_instruction="已经逾期",
        creator_id=uuid4(),
        assignee_id=assignee_id,
        visibility=TaskVisibility.PERSONAL,
        status=TaskStatus.TODO,
        deadline=now - timedelta(minutes=1),
    )
    completed = Task(
        id=uuid4(),
        title="已完成",
        original_instruction="已完成",
        creator_id=uuid4(),
        assignee_id=assignee_id,
        visibility=TaskVisibility.PERSONAL,
        status=TaskStatus.COMPLETED,
        deadline=now - timedelta(days=1),
    )

    events = collect_overdue_events([overdue, completed], now=now)

    assert len(events) == 1
    assert events[0].task_id == overdue.id
    assert events[0].assignee_id == assignee_id
    assert events[0].occurred_at == now
