from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest

from huiyang.domain.models import Task, TaskStatus, TaskVisibility


def make_task(title, status, deadline=None):
    return Task(
        id=uuid4(),
        title=title,
        original_instruction=title,
        creator_id=uuid4(),
        assignee_id=uuid4(),
        visibility=TaskVisibility.TEAM,
        status=status,
        deadline=deadline,
    )


def test_weekly_summary_reports_progress_without_management_advice() -> None:
    try:
        summaries = import_module("huiyang.services.summaries")
    except ModuleNotFoundError:
        pytest.fail("weekly summary service is missing")
    now = datetime(2026, 10, 4, 5, 0, tzinfo=UTC)
    tasks = [
        make_task("已交付", TaskStatus.COMPLETED),
        make_task("开发中", TaskStatus.IN_PROGRESS),
        make_task("等待凭据", TaskStatus.BLOCKED),
        make_task("已经逾期", TaskStatus.TODO, now - timedelta(hours=1)),
    ]

    text = summaries.build_weekly_summary("飞书机器人", tasks, now=now)

    assert "已完成（1）：已交付" in text
    assert "进行中（1）：开发中" in text
    assert "阻塞（1）：等待凭据" in text
    assert "已逾期（1）：已经逾期" in text
    assert "建议" not in text
    assert "评价" not in text


def test_scheduler_uses_configured_timezone_and_sunday_20_clock() -> None:
    try:
        scheduling = import_module("huiyang.services.scheduling")
    except ModuleNotFoundError:
        pytest.fail("scheduler configuration is missing")

    class FakeScheduler:
        def __init__(self):
            self.jobs = []

        def add_job(self, function, trigger, **kwargs):
            self.jobs.append((function, trigger, kwargs))

    scheduler = FakeScheduler()
    reminder_job = object()
    summary_job = object()
    scheduling.configure_jobs(
        scheduler,
        reminder_job=reminder_job,
        weekly_summary_job=summary_job,
        timezone="Asia/Shanghai",
    )

    assert scheduler.jobs[0][1] == "interval"
    assert scheduler.jobs[0][2]["seconds"] == 30
    assert scheduler.jobs[1][1] == "cron"
    assert scheduler.jobs[1][2] == {
        "day_of_week": "sun",
        "hour": 20,
        "minute": 0,
        "timezone": "Asia/Shanghai",
        "id": "weekly-project-summary",
        "replace_existing": True,
    }
