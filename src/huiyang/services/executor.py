from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from huiyang.i18n import t
from huiyang.agent.schemas import ActionType, StructuredAction
from huiyang.domain.models import Task, TaskVisibility
from huiyang.services.secretary import ExecutionResult, IncomingMessage, TodoView
from huiyang.services.todos import CreateTaskCommand


@dataclass(frozen=True, slots=True)
class UserIdentity:
    id: UUID
    feishu_user_id: str
    display_name: str


class UserDirectory(Protocol):
    async def by_feishu_id(self, feishu_user_id: str) -> UserIdentity | None: ...
    async def by_id(self, user_id: UUID) -> UserIdentity | None: ...


class TaskQueries(Protocol):
    async def get(self, task_id: UUID) -> Task | None: ...
    async def list_active_by_assignee(self, assignee_id: UUID) -> list[Task]: ...


class TodoActions(Protocol):
    async def create(self, command: CreateTaskCommand) -> Task: ...
    async def update(self, **kwargs: Any) -> Task: ...
    async def delete(self, **kwargs: Any) -> None: ...


class BusinessActionExecutor:
    def __init__(
        self,
        *,
        todo_service: TodoActions,
        tasks: TaskQueries,
        users: UserDirectory,
        admin_feishu_user_id: str = "",
    ) -> None:
        self._todos = todo_service
        self._tasks = tasks
        self._users = users
        self._admin_feishu_user_id = admin_feishu_user_id

    async def execute(
        self,
        action: StructuredAction,
        message: IncomingMessage,
    ) -> ExecutionResult:
        actor = await self._require_user(message.sender_id)

        if action.action_type is ActionType.CREATE_TASK:
            payload = action.payload
            assignee_id = str(
                payload.get("assignee_feishu_user_id") or message.sender_id
            )
            assignee = await self._require_user(assignee_id)
            title = str(payload.get("title") or "").strip()
            if not title:
                raise ValueError("create_task requires title")
            visibility = TaskVisibility(
                str(
                    payload.get("visibility")
                    or (
                        "personal"
                        if message.chat_type == "p2p"
                        else "team"
                    )
                )
            )
            created = await self._todos.create(
                CreateTaskCommand(
                    title=title,
                    original_instruction=message.text,
                    creator_id=actor.id,
                    assignee_id=assignee.id,
                    actor_feishu_user_id=actor.feishu_user_id,
                    assignee_feishu_user_id=assignee.feishu_user_id,
                    visibility=visibility,
                    description=self._optional_text(payload.get("description")),
                    project_id=action.project_id or self._parse_uuid(payload.get("project_id")),
                    source_chat_id=(
                        message.chat_id
                        if visibility is TaskVisibility.TEAM
                        else None
                    ),
                    priority=self._optional_text(payload.get("priority")),
                    deadline=self._parse_datetime(payload.get("deadline")),
                    reminder_times=self._parse_datetime_list(
                        payload.get("reminder_times")
                    ),
                )
            )
            action.task_id = created.id
            return await self._with_active(
                t("已创建任务「{title}」。", title=title),
                assignee,
            )

        if action.action_type is ActionType.LIST_TASKS:
            requested_id = str(
                action.payload.get("assignee_feishu_user_id") or message.sender_id
            )
            if (
                requested_id != message.sender_id
                and message.sender_id != self._admin_feishu_user_id
            ):
                raise PermissionError("普通用户只能查看自己的任务")
            assignee = await self._require_user(requested_id)
            active = await self._tasks.list_active_by_assignee(assignee.id)
            return ExecutionResult(
                outcome=t("当前共有 {count} 个进行中的任务。", count=len(active)),
                resolved_task_ids=[str(task.id) for task in active],
                affected_todos={
                    assignee.display_name: [self._view(task) for task in active]
                },
            )

        task = await self._require_task(action.task_id)
        assignee = await self._require_user_id(task.assignee_id)
        if action.action_type is ActionType.UPDATE_TASK:
            target = action.payload.get("assignee_feishu_user_id")
            new_assignee = await self._require_user(str(target)) if target else assignee
            if new_assignee.id != assignee.id and actor.feishu_user_id != self._admin_feishu_user_id:
                raise PermissionError("只有管理员可以重新分配他人的任务")
            changes = self._normalize_changes(action.payload)
            if target:
                changes["assignee_id"] = new_assignee.id
            await self._todos.update(
                task_id=task.id,
                actor_feishu_user_id=actor.feishu_user_id,
                assignee_feishu_user_id=assignee.feishu_user_id,
                changes=changes,
                now=message.received_at,
            )
            result = await self._with_active(t("已修改任务。"), assignee)
            if new_assignee.id != assignee.id:
                other = await self._with_active("", new_assignee)
                result.affected_todos.update(other.affected_todos)
                result.resolved_task_ids.extend(other.resolved_task_ids)
            return result

        if action.action_type is ActionType.DELETE_TASK:
            await self._todos.delete(
                task_id=task.id,
                actor_feishu_user_id=actor.feishu_user_id,
                assignee_feishu_user_id=assignee.feishu_user_id,
                now=message.received_at,
            )
            return await self._with_active(
                t("已删除任务「{title}」。", title=task.title),
                assignee,
            )

        raise ValueError(f"Unsupported action type: {action.action_type}")

    async def _with_active(
        self,
        outcome: str,
        assignee: UserIdentity,
    ) -> ExecutionResult:
        active = await self._tasks.list_active_by_assignee(assignee.id)
        return ExecutionResult(
            outcome=outcome,
            resolved_task_ids=[str(task.id) for task in active],
            affected_todos={
                assignee.display_name: [self._view(task) for task in active]
            },
        )

    async def _require_user(self, feishu_user_id: str) -> UserIdentity:
        user = await self._users.by_feishu_id(feishu_user_id)
        if user is None:
            raise LookupError(f"User {feishu_user_id} not found")
        return user

    async def _require_user_id(self, user_id: UUID) -> UserIdentity:
        user = await self._users.by_id(user_id)
        if user is None:
            raise LookupError(f"User {user_id} not found")
        return user

    async def _require_task(self, task_id: UUID | None) -> Task:
        if task_id is None:
            raise ValueError("Task action requires task_id")
        task = await self._tasks.get(task_id)
        if task is None:
            raise LookupError(f"Task {task_id} not found")
        return task

    @staticmethod
    def _view(task: Task) -> TodoView:
        return TodoView(
            title=task.title,
            deadline_text=(
                task.deadline.isoformat() if task.deadline else t("无截止时间")
            ),
            status=t(task.status.value),
        )

    @classmethod
    def _normalize_changes(cls, payload: dict[str, object]) -> dict[str, object]:
        changes = dict(payload)
        changes.pop("assignee_feishu_user_id", None)
        changes.pop("assignee_name", None)
        changes.pop("task_id", None)
        changes.pop("understanding", None)
        if "deadline" in changes:
            changes["deadline"] = cls._parse_datetime(changes["deadline"])
        if "reminder_times" in changes:
            changes["reminder_times"] = cls._parse_datetime_list(
                changes["reminder_times"]
            )
        if "project_id" in changes:
            changes["project_id"] = cls._parse_uuid(changes["project_id"])
        return changes

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None or value == "":
            return None
        parsed = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(str(value))
        )
        if parsed.tzinfo is None:
            raise ValueError("Datetime values must include a timezone")
        return parsed

    @classmethod
    def _parse_datetime_list(cls, value: object) -> list[datetime] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("reminder_times must be a list")
        parsed = [cls._parse_datetime(item) for item in value]
        if any(item is None for item in parsed):
            raise ValueError("reminder_times cannot contain null")
        return [item for item in parsed if item is not None]

    @staticmethod
    def _parse_uuid(value: object) -> UUID | None:
        if value is None or value == "":
            return None
        return value if isinstance(value, UUID) else UUID(str(value))

    @staticmethod
    def _optional_text(value: object) -> str | None:
        return None if value is None else str(value)
