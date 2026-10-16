from sqlalchemy import Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from huiyang.domain.base import Base
from huiyang.team.model import empty_board


class TeamSpace(Base):
    __tablename__ = "team_spaces"
    chat_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    board: Mapped[dict] = mapped_column(JSON, default=empty_board)
    people: Mapped[dict] = mapped_column(JSON, default=dict)


class TeamSession(Base):
    __tablename__ = "team_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255))
    csrf: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class TeamOAuthState(Base):
    __tablename__ = "team_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    chat_id: Mapped[str] = mapped_column(String(255))
    verifier: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
