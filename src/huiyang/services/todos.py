from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from huiyang.domain.models import Task, TaskStatus, TaskVisibility
from huiyang.domain.persistence import Reminder
from huiyang.services.permissions import PermissionService


class TaskRepository(Protocol):
    async def add(self, task: Task) -> Task: ...
    async def get(self, task_id: UUID) -> Task | None: ...
    async def save(self, task: Task) -> Task: ...
    async def delete(self, task_id: UUID) -> None: ...


class ReminderRepository(Protocol):
    async def add_many(self, reminders: list[Reminder]) -> None: ...
    async def cancel_pending(
        self,
        task_id: UUID,
        *,
        canceled_at: datetime,
    ) -> None: ...


@dataclass(slots=True)
class CreateTaskCommand:
    title: str
    original_instruction: str
    creator_id: UUID
    assignee_id: UUID
    actor_feishu_user_id: str
    assignee_feishu_user_id: str
    visibility: TaskVisibility
    description: str | None = None
    project_id: UUID | None = None
    source_chat_id: str | None = None
    priority: str | None = None
    deadline: datetime | None = None
    reminder_times: list[datetime] | None = field(default=None)


class TodoService:
    def __init__(
        self,
        *,
        tasks: TaskRepository,
        reminders: ReminderRepository,
        permissions: PermissionService,
    ) -> None:
        self._tasks = tasks
        self._reminders = reminders
        self._permissions = permissions

    async def create(self, command: CreateTaskCommand) -> Task:
        self._permissions.assert_can_manage(
            actor_feishu_user_id=command.actor_feishu_user_id,
            assignee_feishu_user_id=command.assignee_feishu_user_id,
        )
        task = Task(
            id=uuid4(),
            title=command.title,
            original_instruction=command.original_instruction,
            description=command.description,
            assignee_id=command.assignee_id,
            creator_id=command.creator_id,
            project_id=command.project_id,
            visibility=command.visibility,
            source_chat_id=command.source_chat_id,
            priority=command.priority,
            status=TaskStatus.TODO,
            deadline=command.deadline,
        )
        task = await self._tasks.add(task)

        reminder_times = command.reminder_times
        if reminder_times is None and command.deadline is not None:
            reminder_times = [
                command.deadline - timedelta(hours=1),
                command.deadline,
            ]
        if reminder_times:
            destination = (
                "private"
                if command.visibility is TaskVisibility.PERSONAL
                else "group"
            )
            await self._reminders.add_many(
                [
                    Reminder(
                        id=uuid4(),
                        task_id=task.id,
                        scheduled_for=scheduled_for,
                        kind=(
                            "custom"
                            if command.reminder_times is not None
                            else "default"
                        ),
                        destination=destination,
                        destination_chat_id=(
                            command.source_chat_id if destination == "group" else None
                        ),
                    )
                    for scheduled_for in reminder_times
                ]
            )
        return task
    async def set_status(
        self,
        *,
        task_id: UUID,
        status: TaskStatus,
        actor_feishu_user_id: str,
        assignee_feishu_user_id: str,
        blocked_reason: str | None = None,
        now: datetime,
    ) -> Task:
        self._permissions.assert_can_manage(
            actor_feishu_user_id=actor_feishu_user_id,
            assignee_feishu_user_id=assignee_feishu_user_id,
        )
        task = await self._tasks.get(task_id)
        if task is None:
            raise LookupError(f"Task {task_id} not found")
        task.set_status(status, blocked_reason=blocked_reason, now=now)
        task = await self._tasks.save(task)
        if status in {TaskStatus.COMPLETED, TaskStatus.CANCELED}:
            await self._reminders.cancel_pending(task.id, canceled_at=now)
        return task

    async def update(
        self,
        *,
        task_id: UUID,
        actor_feishu_user_id: str,
        assignee_feishu_user_id: str,
        changes: dict[str, object],
        now: datetime,
    ) -> Task:
        self._permissions.assert_can_manage(
            actor_feishu_user_id=actor_feishu_user_id,
            assignee_feishu_user_id=assignee_feishu_user_id,
        )
        task = await self._tasks.get(task_id)
        if task is None:
            raise LookupError(f"Task {task_id} not found")

        allowed = {
            "assignee_id",
            "title",
            "description",
            "project_id",
            "visibility",
            "source_chat_id",
            "priority",
            "deadline",
            "status",
            "blocked_reason",
            "reminder_times",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported task changes: {sorted(unknown)}")

        deadline_changed = "deadline" in changes or "reminder_times" in changes
        route_changed = bool({"assignee_id", "visibility", "source_chat_id"} & set(changes))
        status_value = changes.get("status")
        for field_name in (
            "assignee_id",
            "title",
            "description",
            "project_id",
            "source_chat_id",
            "priority",
            "deadline",
        ):
            if field_name in changes:
                setattr(task, field_name, changes[field_name])
        if "visibility" in changes:
            task.visibility = TaskVisibility(str(changes["visibility"]))
        if status_value is not None:
            task.set_status(
                TaskStatus(str(status_value)),
                blocked_reason=changes.get("blocked_reason"),
                now=now,
            )

        task = await self._tasks.save(task)
        if route_changed and hasattr(self._reminders, "reroute_pending"):
            await self._reminders.reroute_pending(task)
        is_terminal = task.status in {TaskStatus.COMPLETED, TaskStatus.CANCELED}
        if deadline_changed or is_terminal:
            await self._reminders.cancel_pending(task.id, canceled_at=now)

        if deadline_changed and not is_terminal:
            supplied_times = changes.get("reminder_times")
            reminder_times = (
                list(supplied_times)
                if supplied_times is not None
                else ([task.deadline - timedelta(hours=1), task.deadline] if task.deadline else [])
            )
            destination = (
                "private"
                if task.visibility is TaskVisibility.PERSONAL
                else "group"
            )
            await self._reminders.add_many(
                [
                    Reminder(
                        id=uuid4(),
                        task_id=task.id,
                        scheduled_for=scheduled_for,
                        kind="custom" if supplied_times is not None else "default",
                        destination=destination,
                        destination_chat_id=(
                            task.source_chat_id if destination == "group" else None
                        ),
                    )
                    for scheduled_for in reminder_times
                ]
            )
        return task

    async def delete(
        self,
        *,
        task_id: UUID,
        actor_feishu_user_id: str,
        assignee_feishu_user_id: str,
        now: datetime,
    ) -> None:
        self._permissions.assert_can_manage(
            actor_feishu_user_id=actor_feishu_user_id,
            assignee_feishu_user_id=assignee_feishu_user_id,
        )
        task = await self._tasks.get(task_id)
        if task is None:
            raise LookupError(f"Task {task_id} not found")
        await self._reminders.cancel_pending(task.id, canceled_at=now)
        await self._tasks.delete(task.id)
