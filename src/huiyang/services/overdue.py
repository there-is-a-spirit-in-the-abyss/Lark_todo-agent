from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huiyang.domain.models import Task, TaskVisibility


@dataclass(frozen=True, slots=True)
class OverdueEvent:
    task_id: UUID
    assignee_id: UUID
    title: str
    deadline: datetime
    visibility: TaskVisibility
    source_chat_id: str | None
    occurred_at: datetime


def collect_overdue_events(
    tasks: list[Task],
    *,
    now: datetime,
) -> list[OverdueEvent]:
    return [
        OverdueEvent(
            task_id=task.id,
            assignee_id=task.assignee_id,
            title=task.title,
            deadline=task.deadline,
            visibility=task.visibility,
            source_chat_id=task.source_chat_id,
            occurred_at=now,
        )
        for task in tasks
        if task.deadline is not None and task.is_overdue(now)
    ]
