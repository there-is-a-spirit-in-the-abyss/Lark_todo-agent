from __future__ import annotations

from collections.abc import Callable
from typing import Any


def configure_jobs(
    scheduler: Any,
    *,
    reminder_job: Callable[[], Any],
    weekly_summary_job: Callable[[], Any],
    timezone: str,
) -> None:
    scheduler.add_job(
        reminder_job,
        "interval",
        seconds=30,
        id="due-reminders",
        replace_existing=True,
    )
    if weekly_summary_job is not None:
        scheduler.add_job(
            weekly_summary_job,
            "cron",
            day_of_week="sun",
            hour=20,
            minute=0,
            timezone=timezone,
            id="weekly-project-summary",
            replace_existing=True,
        )
