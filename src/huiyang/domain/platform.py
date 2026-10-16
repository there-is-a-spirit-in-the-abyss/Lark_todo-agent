"""Transport state, separate from tasks and project business rules."""
from datetime import UTC, datetime
from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from huiyang.domain.base import Base


class FeishuInbox(Base):
    __tablename__ = "feishu_inbox"
    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ChatObservation(Base):
    __tablename__ = "chat_observations"
    message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(255), index=True)
    chat_type: Mapped[str] = mapped_column(String(20))
    sender_user_id: Mapped[str] = mapped_column(String(255))
    sender_open_id: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
