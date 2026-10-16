"""Small single-process jobs, backed by database delivery state."""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select

from huiyang.adapters.feishu_api import delivery_key
from huiyang.domain.models import Task, TaskVisibility
from huiyang.i18n import preferred_language
from huiyang.domain.persistence import Project
from huiyang.domain.platform import PlatformSetting
from huiyang.repositories.sqlalchemy import SqlAlchemyDueReminderRepository
from huiyang.services.summaries import build_weekly_summary


class BackgroundJobs:
    def __init__(self, sessions, adapter, settings):
        self.sessions = sessions
        self.adapter = adapter
        self.settings = settings

    async def reminders(self):
        now = datetime.now(UTC)
        async with self.sessions() as session:
            repo = SqlAlchemyDueReminderRepository(session, personal_only=self.settings.team_web_enabled,
                                                   language=self.settings.app_language)
            for item in await repo.due(now):
                token = delivery_key.set("reminder:" + item.reminder_id)
                try:
                    if item.destination == "private":
                        await self.adapter.send_private(item.assignee_user_id, item.text)
                    elif item.chat_id:
                        await self.adapter.send_group(item.chat_id, item.text, mention_user_id=item.assignee_user_id)
                    else:
                        raise ValueError("Team reminder missing source group")
                    await repo.mark_triggered(item.reminder_id, triggered_at=now)
                    await session.commit()
                finally:
                    delivery_key.reset(token)

    async def weekly_summary(self):
        if self.settings.team_web_enabled:
            return
        now = datetime.now(UTC)
        week = now.astimezone(ZoneInfo(self.settings.app_timezone)).date().isoformat()
        async with self.sessions() as session:
            projects = list(await session.scalars(select(Project).where(Project.summary_chat_id.is_not(None))))
            for project in projects:
                key = f"summary:{project.id}:{week}"
                if await session.get(PlatformSetting, key):
                    continue
                tasks = list(await session.scalars(select(Task).where(
                    Task.project_id == project.id, Task.visibility == TaskVisibility.TEAM,
                )))
                token = delivery_key.set(key)
                try:
                    language = await preferred_language(session, private=False,
                        identity=project.summary_chat_id, default=self.settings.app_language)
                    await self.adapter.send_group(project.summary_chat_id,
                        build_weekly_summary(project.name, tasks, now=now, language=language))
                    session.add(PlatformSetting(key=key, value="sent"))
                    await session.commit()
                finally:
                    delivery_key.reset(token)
