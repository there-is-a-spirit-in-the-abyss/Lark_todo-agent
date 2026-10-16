"""SDK event -> durable inbox -> normalized message -> one business transaction."""
import asyncio
import logging
import re
from urllib.parse import quote
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from huiyang.adapters.events import normalize_event, resolve_sender_identity
from huiyang.i18n import (LANGUAGES, current_language, language_scope,
                          preferred_language, save_language, t)
from huiyang.adapters.feishu_api import delivery_key
from huiyang.agent.schemas import ActionType
from huiyang.domain.models import Task, TaskVisibility
from huiyang.domain.persistence import Project, User, ConversationMemory
from huiyang.domain.platform import ChatObservation, FeishuInbox
from huiyang.repositories.memory import SqlAlchemyMemoryRepository
from huiyang.repositories.sqlalchemy import SqlAlchemyTaskRepository, SqlAlchemyReminderRepository, SqlAlchemyUserDirectory
from huiyang.services.enrollment import upsert_sender, bind_group_admin_if_unset, effective_admin
from huiyang.services.executor import BusinessActionExecutor
from huiyang.services.memory import MemoryAwareSecretary
from huiyang.services.permissions import PermissionService
from huiyang.services.projects import ProjectActionRouter
from huiyang.services.secretary import SecretaryAgent
from huiyang.services.todos import TodoService

log = logging.getLogger(__name__)


class PlatformGateway:
    def __init__(self, sessions, interpreter, adapter, settings, *, bot_open_id=""):
        self.sessions = sessions
        self.interpreter = interpreter
        self.adapter = adapter
        self.settings = settings
        self.bot_open_id = bot_open_id

    async def prepare(self, session, row):
        normalized = normalize_event(row.payload, bot_open_id=self.bot_open_id)
        if normalized is None:
            row.state = "done"
            return
        message = normalized.message
        private = message.chat_type == "p2p"
        identity = message.sender_id if private else message.chat_id
        language = await preferred_language(session, private=private, identity=identity,
                                            default=self.settings.app_language)
        # Team-web groups keep the entry-only path, with no group preferences.
        team_group = self.settings.team_web_enabled and not private
        if team_group:
            language = self.settings.app_language
        command = re.sub(r"^@\S+\s+", "", message.text.strip())
        if (not team_group and (private or message.mentioned_bot)
                and command.startswith('/language')):
            parts = command.split()
            if len(parts) == 2 and parts[0] == '/language' and parts[1] in LANGUAGES:
                language = parts[1]
                await save_language(session, private=private, identity=identity, language=language)
                text = t('语言已切换为简体中文。', language=language)
            else:
                text = t('用法：/language zh-CN 或 /language en-US', language=language)
            row.response = {'target': identity, 'private': private, 'text': text}
            row.state = 'ready'
            row.payload = {}
            return
        with language_scope(language):
            return await self._prepare(session, row)

    async def _prepare(self, session, row):
        normalized = normalize_event(row.payload, bot_open_id=self.bot_open_id)
        if normalized is None:
            row.state = "done"
            return
        message = normalized.message
        duplicate = await session.get(ChatObservation, message.message_id)
        if duplicate is not None:
            row.state = "done"
            return
        if self.settings.team_web_enabled and message.chat_type == "group":
            requested = message.mentioned_bot and any(
                word in message.text.lower() for word in ("团队任务", "团队todo", "team tasks", "team todo"))
            text = None
            if requested and self.settings.team_public_url:
                text = t("团队任务：") + self.settings.team_public_url.rstrip("/") + "/team/" + quote(message.chat_id, safe="")
            row.response = ({"target": message.chat_id, "private": False,
                             "team_entry": True, "text": text} if text else None)
            row.state = "ready" if text else "done"
            row.payload = {}
            return
        await bind_group_admin_if_unset(session, message, self.adapter)
        # Owner discovery must persist even if contact-name lookup or the LLM fails.
        await session.commit()
        message = await resolve_sender_identity(message, self.adapter)
        user = await upsert_sender(session, message)
        # Preserve discovery even if the model or outbound transport later fails.
        await session.commit()
        is_binding = message.text.startswith("绑定管理员 ")
        session.add(ChatObservation(
            message_id=message.message_id, chat_id=message.chat_id,
            chat_type=message.chat_type, sender_user_id=message.sender_id,
            sender_open_id=message.sender_open_id,
            text="[管理员身份绑定]" if is_binding else message.text,
            created_at=message.received_at,
        ))
        await session.flush()
        text = None
        if message.text.startswith(("登记 ", "绑定管理员 ")):
            text = t("已自动同步飞书名称「{name}」，无需登记或绑定码。", name=user.display_name)
        if text is None:
            context = await self.context(session, message, user)
            admin = await effective_admin(session, self.settings)
            tasks = SqlAlchemyTaskRepository(session, personal_only=self.settings.team_web_enabled)
            executor = BusinessActionExecutor(
                todo_service=TodoService(tasks=tasks, reminders=SqlAlchemyReminderRepository(session),
                                         permissions=PermissionService(admin)),
                tasks=tasks, users=SqlAlchemyUserDirectory(session), admin_feishu_user_id=admin,
            )
            router = ProjectActionRouter(executor, session, admin)
            if self.settings.team_web_enabled:
                from huiyang.team.personal import PersonalChatExecutor
                router = PersonalChatExecutor(router)
            service = MemoryAwareSecretary(
                delegate=SecretaryAgent(self.interpreter, router),
                memories=SqlAlchemyMemoryRepository(session, personal_only=self.settings.team_web_enabled),
            )
            # Savepoint ensures any denied/invalid action cannot partially mutate data.
            try:
                async with session.begin_nested():
                    response = await service.handle(message, context=context)
                    text = response.text
            except PermissionError:
                text = t("我理解你希望操作任务；权限检查未通过，只能管理自己负责的任务。")
            except ValueError:
                text = t("未执行任务操作：解析结果未通过校验，请补充或明确指令。")
            except LookupError:
                text = t("未执行任务操作：相关人员、任务或项目尚未找到，请明确对象。")
        row.response = ({"target": message.sender_id if message.chat_type == "p2p" else message.chat_id,
                         "private": message.chat_type == "p2p", "text": text} if text else None)
        row.state = "ready" if text else "done"
        # Raw event no longer needed once normalized facts are committed.
        row.payload = {}

    async def context(self, session, message, user):
        observations = list(await session.scalars(select(ChatObservation).where(
            ChatObservation.chat_id == message.chat_id,
            ChatObservation.chat_type == message.chat_type,
            or_(ChatObservation.chat_type == "group",
                ChatObservation.sender_user_id == message.sender_id),
            ChatObservation.created_at >= message.received_at - timedelta(days=7),
        ).order_by(ChatObservation.created_at.desc()).limit(40)))
        facts = list(await session.scalars(select(Task).where(
            ((Task.assignee_id == user.id) & (Task.visibility == TaskVisibility.PERSONAL))
            if self.settings.team_web_enabled else
            or_(Task.assignee_id == user.id, Task.visibility == TaskVisibility.TEAM)
        ).order_by(Task.updated_at.desc()).limit(150)))
        people = list(await session.scalars(select(User).limit(100)))
        project_query = select(Project)
        if self.settings.team_web_enabled:
            personal_projects = select(Task.project_id).where(
                Task.assignee_id == user.id, Task.visibility == TaskVisibility.PERSONAL)
            own_creations = select(ConversationMemory.resolved_project_id).where(
                ConversationMemory.chat_id == message.chat_id,
                ConversationMemory.sender_id == message.sender_id,
                ConversationMemory.action_data["action_type"].as_string() == "create_project",
                ConversationMemory.resolved_project_id.is_not(None),
                ConversationMemory.resolved_project_id.not_in(select(Task.project_id).where(
                    Task.visibility == TaskVisibility.TEAM, Task.project_id.is_not(None))))
            project_query = project_query.where(or_(Project.id.in_(personal_projects),
                                                     Project.id.in_(own_creations)))
        projects = list(await session.scalars(project_query.limit(100)))
        return {
            "language": current_language(),
            "timezone": self.settings.app_timezone,
            "recent_chat": [{"sender_user_id": item.sender_user_id, "text": item.text,
                             "time": item.created_at.isoformat()} for item in reversed(observations)],
            "users": [{"internal_id": str(item.id), "user_id": item.feishu_user_id,
                       "name": item.display_name} for item in people],
            "projects": [{"id": str(item.id), "name": item.name} for item in projects],
            "tasks": [{"id": str(item.id), "title": item.title, "assignee_id": str(item.assignee_id),
                       "project_id": str(item.project_id) if item.project_id else None,
                       "visibility": item.visibility.value, "status": item.status.value,
                       "deadline": item.deadline.isoformat() if item.deadline else None}
                      for item in facts],
        }

    async def process_one(self):
        now = datetime.now(UTC)
        async with self.sessions() as session:
            row = await session.scalar(select(FeishuInbox).where(
                FeishuInbox.state.in_(["pending", "ready"]),
                or_(FeishuInbox.retry_at.is_(None), FeishuInbox.retry_at <= now),
            ).order_by(FeishuInbox.created_at).limit(1))
            if row is None:
                return False
            event_id = row.event_id
            try:
                if row.state == "pending":
                    await self.prepare(session, row)
                    await session.commit()
                if row.state == "ready" and row.response:
                    if (self.settings.team_web_enabled and not row.response["private"]
                            and not row.response.get("team_entry")):
                        row.state = "done"
                        await session.commit()
                        return True
                    token = delivery_key.set("event:" + event_id)
                    try:
                        if row.response["private"]:
                            await self.adapter.send_private(row.response["target"], row.response["text"])
                        else:
                            await self.adapter.send_group(row.response["target"], row.response["text"])
                    finally:
                        delivery_key.reset(token)
                    row.state = "done"
                    await session.commit()
                return True
            except Exception as error:
                await session.rollback()
                row = await session.get(FeishuInbox, event_id)
                row.attempts += 1
                row.error_code = type(error).__name__
                row.retry_at = now + timedelta(seconds=min(300, 2 ** min(row.attempts, 8)))
                if row.attempts >= 8:
                    row.state = "failed"
                await session.commit()
                log.warning("Event %s failed (%s); attempts=%s", event_id, row.error_code, row.attempts)
                return False

    async def run(self):
        while True:
            try:
                worked = await self.process_one()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.warning("Inbox worker unavailable (%s)", type(error).__name__)
                worked = False
            await asyncio.sleep(0 if worked else 1)
