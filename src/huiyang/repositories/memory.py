from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from huiyang.domain.persistence import ConversationMemory
from huiyang.domain.models import Task, TaskVisibility


class SqlAlchemyMemoryRepository:
    def __init__(self, session: AsyncSession, *, personal_only=False) -> None:
        self._session = session
        self._personal_only = personal_only

    async def add(self, memory: ConversationMemory) -> ConversationMemory:
        self._session.add(memory)
        await self._session.flush()
        return memory

    async def relevant(
        self,
        *,
        chat_id: str,
        sender_id: str,
        now: datetime,
        limit: int = 20,
    ) -> list[ConversationMemory]:
        result = await self._session.scalars(
            select(ConversationMemory)
            .where(
                ConversationMemory.chat_id == chat_id,
                ConversationMemory.sender_id == sender_id if self._personal_only else True,
                or_(
                    ConversationMemory.sender_id == sender_id,
                    ConversationMemory.scope == "project",
                ),
                or_(
                    ConversationMemory.scope == "project",
                    ConversationMemory.expires_at.is_(None),
                    ConversationMemory.expires_at > now,
                ),
            )
            .order_by(ConversationMemory.created_at.desc())
            .limit(limit)
        )
        memories = list(result)
        if not self._personal_only:
            return memories
        personal = {str(tid) for tid in await self._session.scalars(
            select(Task.id).where(Task.visibility == TaskVisibility.PERSONAL))}
        personal_projects = set(await self._session.scalars(
            select(Task.project_id).where(Task.visibility == TaskVisibility.PERSONAL,
                                           Task.project_id.is_not(None))))
        team_projects = set(await self._session.scalars(
            select(Task.project_id).where(Task.visibility == TaskVisibility.TEAM,
                                           Task.project_id.is_not(None))))
        safe = []
        for memory in memories:
            action = memory.action_data or {}
            payload = action.get("payload") or {}
            if action.get("action_type") == "weekly_summary" or payload.get("visibility") == "team":
                continue
            references = set(memory.resolved_task_ids or [])
            if action.get("task_id"):
                references.add(action["task_id"])
            if not references.issubset(personal):
                continue
            if memory.resolved_project_id and memory.resolved_project_id not in personal_projects:
                own_creation = (action.get("action_type") == "create_project"
                                and memory.resolved_project_id not in team_projects)
                if not own_creation:
                    continue
            safe.append(memory)
        return safe
