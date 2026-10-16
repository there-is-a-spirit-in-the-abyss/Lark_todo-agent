from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from huiyang.repositories.memory import SqlAlchemyMemoryRepository
from huiyang.repositories.sqlalchemy import (
    SqlAlchemyReminderRepository,
    SqlAlchemyTaskRepository,
    SqlAlchemyUserDirectory,
)
from huiyang.services.executor import BusinessActionExecutor
from huiyang.services.memory import MemoryAwareSecretary
from huiyang.services.permissions import PermissionService
from huiyang.services.enrollment import effective_admin
from huiyang.services.secretary import (
    ActionInterpreter,
    IncomingMessage,
    SecretaryAgent,
    SecretaryResponse,
)
from huiyang.services.todos import TodoService


class SessionSecretary:
    """Build one transactional Secretary Agent for each incoming message."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        interpreter: ActionInterpreter,
        admin_feishu_user_id: str = "",
    ) -> None:
        self._session_factory = session_factory
        self._interpreter = interpreter
        self._admin_feishu_user_id = admin_feishu_user_id

    async def handle(
        self,
        message: IncomingMessage,
        *,
        context: dict[str, Any],
    ) -> SecretaryResponse:
        async with self._session_factory() as session:
            tasks = SqlAlchemyTaskRepository(session)
            reminders = SqlAlchemyReminderRepository(session)
            admin_id = await effective_admin(session) or self._admin_feishu_user_id
            permissions = PermissionService(admin_id)
            todos = TodoService(
                tasks=tasks,
                reminders=reminders,
                permissions=permissions,
            )
            executor = BusinessActionExecutor(
                todo_service=todos,
                tasks=tasks,
                users=SqlAlchemyUserDirectory(session),
                admin_feishu_user_id=admin_id,
            )
            agent = SecretaryAgent(self._interpreter, executor)
            service = MemoryAwareSecretary(
                delegate=agent,
                memories=SqlAlchemyMemoryRepository(session),
            )
            response = await service.handle(message, context=context)
            await session.commit()
            return response
