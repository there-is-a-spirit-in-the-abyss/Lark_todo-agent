from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest


def load_models():
    try:
        return import_module("huiyang.domain.models")
    except ModuleNotFoundError:
        pytest.fail("domain models are missing")


def test_overdue_is_derived_from_deadline_and_terminal_status() -> None:
    models = load_models()
    now = datetime(2026, 10, 4, 4, 0, tzinfo=UTC)
    task = models.Task(
        title="完成首页",
        original_instruction="周五把首页做出来",
        assignee_id=uuid4(),
        creator_id=uuid4(),
        visibility=models.TaskVisibility.TEAM,
        status=models.TaskStatus.BLOCKED,
        deadline=now - timedelta(minutes=1),
    )

    assert task.is_overdue(now) is True

    task.set_status(models.TaskStatus.COMPLETED, now=now)
    assert task.is_overdue(now) is False


def test_blocked_metadata_tracks_blocked_state_only() -> None:
    models = load_models()
    now = datetime(2026, 10, 4, 4, 0, tzinfo=UTC)
    task = models.Task(
        title="接入飞书",
        original_instruction="接入飞书",
        assignee_id=uuid4(),
        creator_id=uuid4(),
        visibility=models.TaskVisibility.PERSONAL,
        status=models.TaskStatus.TODO,
    )

    task.set_status(models.TaskStatus.BLOCKED, blocked_reason="等待凭据", now=now)
    assert task.blocked_reason == "等待凭据"
    assert task.blocked_since == now

    task.set_status(models.TaskStatus.IN_PROGRESS, now=now + timedelta(hours=1))
    assert task.blocked_reason is None
    assert task.blocked_since is None
