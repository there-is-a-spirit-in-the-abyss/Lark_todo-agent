from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from huiyang.domain.base import Base




class TaskVisibility(StrEnum):
    PERSONAL = "personal"
    TEAM = "team"


class TaskStatus(StrEnum):
    TODO = "待办"
    IN_PROGRESS = "进行中"
    BLOCKED = "阻塞"
    COMPLETED = "已完成"
    CANCELED = "已取消"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255))
    original_instruction: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    creator_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=True, index=True
    )
    visibility: Mapped[TaskVisibility] = mapped_column(
        SqlEnum(
            TaskVisibility,
            native_enum=False,
            length=20,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        )
    )
    source_chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        SqlEnum(
            TaskStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=TaskStatus.TODO,
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    def is_overdue(self, now: datetime | None = None) -> bool:
        if self.deadline is None or self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.CANCELED,
        }:
            return False
        deadline = self.deadline
        if deadline.tzinfo is None:  # SQLite test backend returns UTC-naive timestamps
            deadline = deadline.replace(tzinfo=UTC)
        return deadline < (now or datetime.now(UTC))

    def set_status(
        self,
        status: TaskStatus,
        *,
        blocked_reason: str | None = None,
        now: datetime | None = None,
    ) -> None:
        self.status = status
        if status is TaskStatus.BLOCKED:
            self.blocked_reason = blocked_reason
            self.blocked_since = now or datetime.now(UTC)
        else:
            self.blocked_reason = None
            self.blocked_since = None


from huiyang.domain.persistence import ConversationMemory, Project, Reminder, User  # noqa: E402,F401
from huiyang.domain.platform import FeishuInbox, ChatObservation, PlatformSetting  # noqa: E402,F401
from huiyang.team.tables import TeamSpace, TeamSession, TeamOAuthState  # noqa: E402,F401
