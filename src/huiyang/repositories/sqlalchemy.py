from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from huiyang.domain.models import Task, TaskStatus, TaskVisibility
from huiyang.i18n import current_language, preferred_language, t
from huiyang.domain.persistence import Reminder, User
from huiyang.services.reminders import ReminderDelivery
from huiyang.services.executor import UserIdentity


class SqlAlchemyTaskRepository:
    def __init__(self, session: AsyncSession, *, personal_only=False) -> None:
        self._session = session
        self._personal_only = personal_only

    async def add(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        return task

    async def get(self, task_id: UUID) -> Task | None:
        task = await self._session.get(Task, task_id)
        return None if task and self._personal_only and task.visibility != TaskVisibility.PERSONAL else task

    async def save(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        return task

    async def delete(self, task_id: UUID) -> None:
        task = await self.get(task_id)
        if task is not None:
            await self._session.delete(task)
            await self._session.flush()

    async def list_active_by_assignee(self, assignee_id: UUID) -> list[Task]:
        result = await self._session.scalars(
            select(Task)
            .where(
                Task.assignee_id == assignee_id,
                Task.visibility == TaskVisibility.PERSONAL if self._personal_only else True,
                Task.status.not_in([TaskStatus.COMPLETED, TaskStatus.CANCELED]),
            )
            .order_by(Task.deadline.asc().nulls_last(), Task.created_at.asc())
        )
        return list(result)


class SqlAlchemyReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, reminders: list[Reminder]) -> None:
        self._session.add_all(reminders)
        await self._session.flush()

    async def cancel_pending(
        self,
        task_id: UUID,
        *,
        canceled_at: datetime,
    ) -> None:
        await self._cancel_pending(task_id, canceled_at=canceled_at)

    async def reroute_pending(self, task: Task) -> None:
        items = await self._session.scalars(select(Reminder).where(
            Reminder.task_id == task.id, Reminder.triggered_at.is_(None), Reminder.canceled_at.is_(None)))
        for reminder in items:
            reminder.destination = "private" if task.visibility.value == "personal" else "group"
            reminder.destination_chat_id = task.source_chat_id if reminder.destination == "group" else None
        await self._session.flush()

    async def _cancel_pending(
        self,
        task_id: UUID,
        *,
        canceled_at: datetime,
    ) -> None:
        pending = await self._session.scalars(
            select(Reminder).where(
                Reminder.task_id == task_id,
                Reminder.triggered_at.is_(None),
                Reminder.canceled_at.is_(None),
            )
        )
        for reminder in pending:
            reminder.canceled_at = canceled_at
        await self._session.flush()

class SqlAlchemyDueReminderRepository:
    def __init__(self, session: AsyncSession, *, personal_only=False, language=None) -> None:
        self._session = session
        self._personal_only = personal_only
        self._language = language or current_language()

    async def due(self, now: datetime) -> list[ReminderDelivery]:
        rows = await self._session.execute(
            select(Reminder, Task, User)
            .join(Task, Task.id == Reminder.task_id)
            .join(User, User.id == Task.assignee_id)
            .where(
                Reminder.scheduled_for <= now,
                Task.visibility == TaskVisibility.PERSONAL if self._personal_only else True,
                Reminder.destination == "private" if self._personal_only else True,
                Reminder.triggered_at.is_(None),
                Reminder.canceled_at.is_(None),
                Task.status.not_in([TaskStatus.COMPLETED, TaskStatus.CANCELED]),
            )
            .order_by(Reminder.scheduled_for.asc())
        )
        deliveries = []
        for reminder, task, assignee in rows:
            private = reminder.destination == 'private'
            language = await preferred_language(
                self._session, private=private,
                identity=assignee.feishu_user_id if private else reminder.destination_chat_id or '',
                default=self._language)
            if task.deadline is not None and reminder.scheduled_for >= task.deadline:
                text = t("「{title}」已到截止时间", title=task.title, language=language)
            elif reminder.kind == "default":
                text = t("「{title}」将在 1 小时后截止", title=task.title, language=language)
            else:
                text = t("提醒：{title}", title=task.title, language=language)
            deliveries.append(
                ReminderDelivery(
                    reminder_id=str(reminder.id),
                    destination=reminder.destination,
                    assignee_user_id=assignee.feishu_user_id,
                    chat_id=reminder.destination_chat_id,
                    text=text,
                )
            )
        return deliveries

    async def mark_triggered(
        self,
        reminder_id: str,
        *,
        triggered_at: datetime,
    ) -> None:
        reminder = await self._session.get(Reminder, UUID(reminder_id))
        if reminder is None:
            raise LookupError(f"Reminder {reminder_id} not found")
        reminder.triggered_at = triggered_at
        await self._session.flush()

class SqlAlchemyUserDirectory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_feishu_id(self, feishu_user_id: str) -> UserIdentity | None:
        user = await self._session.scalar(
            select(User).where(User.feishu_user_id == feishu_user_id)
        )
        return self._identity(user)

    async def by_id(self, user_id: UUID) -> UserIdentity | None:
        user = await self._session.get(User, user_id)
        return self._identity(user)

    @staticmethod
    def _identity(user: User | None) -> UserIdentity | None:
        if user is None:
            return None
        return UserIdentity(
            id=user.id,
            feishu_user_id=user.feishu_user_id,
            display_name=user.display_name,
        )
