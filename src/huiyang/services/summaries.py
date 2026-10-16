from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from huiyang.i18n import t, language_scope, current_language
from huiyang.domain.models import Task, TaskStatus


def build_weekly_summary(
    project_name: str,
    tasks: Iterable[Task],
    *,
    now: datetime,
    language: str | None = None,
) -> str:
    with language_scope(language or current_language()):
        return _build(project_name, tasks, now=now)


def _build(project_name, tasks, *, now):
    task_list = list(tasks)
    sections = (
        ("已完成", [task.title for task in task_list if task.status == TaskStatus.COMPLETED]),
        ("进行中", [task.title for task in task_list if task.status == TaskStatus.IN_PROGRESS]),
        ("阻塞", [task.title for task in task_list if task.status == TaskStatus.BLOCKED]),
        ("已逾期", [task.title for task in task_list if task.is_overdue(now)]),
    )

    lines = [t("{name} 项目周总结", name=project_name)]
    for label, titles in sections:
        detail = t("、").join(titles) if titles else t("无")
        lines.append(t("{label}（{count}）：{detail}", label=t(label), count=len(titles), detail=detail))
    return "\n".join(lines)
