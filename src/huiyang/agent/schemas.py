from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    IGNORE = "ignore"
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    DELETE_TASK = "delete_task"
    LIST_TASKS = "list_tasks"
    CREATE_PROJECT = "create_project"
    WEEKLY_SUMMARY = "weekly_summary"


class Ambiguity(BaseModel):
    field: str
    question: str


class StructuredAction(BaseModel):
    action_type: ActionType
    understanding: str
    task_id: UUID | None = None
    project_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    ambiguity: Ambiguity | None = None
