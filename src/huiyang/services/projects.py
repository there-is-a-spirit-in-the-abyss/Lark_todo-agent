from uuid import uuid4
from sqlalchemy import select
from huiyang.i18n import t
from huiyang.agent.schemas import ActionType
from huiyang.domain.models import Task, TaskVisibility
from huiyang.domain.persistence import Project
from huiyang.services.secretary import ExecutionResult
from huiyang.services.summaries import build_weekly_summary


class ProjectActionRouter:
    def __init__(self, delegate, session, admin_user_id):
        self.delegate = delegate
        self.session = session
        self.admin_user_id = admin_user_id

    async def execute(self, action, message):
        if action.action_type == ActionType.CREATE_PROJECT:
            name = str(action.payload.get("title") or "").strip()
            if not name:
                raise ValueError("项目名称不能为空")
            project = await self.session.scalar(select(Project).where(Project.name == name))
            if project is None:
                project = Project(id=uuid4(), name=name)
                self.session.add(project)
                await self.session.flush()
            action.project_id = project.id
            return ExecutionResult(outcome=t("已创建项目「{name}」。", name=name))
        if action.action_type == ActionType.WEEKLY_SUMMARY:
            project = await self.session.get(Project, action.project_id) if action.project_id else None
            if project is None:
                raise ValueError("请明确要查看哪个项目")
            tasks = list(await self.session.scalars(select(Task).where(
                Task.project_id == project.id, Task.visibility == TaskVisibility.TEAM,
            )))
            return ExecutionResult(outcome=build_weekly_summary(project.name, tasks, now=message.received_at))
        return await self.delegate.execute(action, message)
