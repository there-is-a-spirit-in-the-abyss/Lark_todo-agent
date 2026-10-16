from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from huiyang.i18n import t, language_scope, current_language
from huiyang.agent.schemas import ActionType, StructuredAction


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    sender_id: str
    chat_id: str
    chat_type: str
    text: str
    received_at: datetime
    message_id: str = ""
    mentioned_bot: bool = False
    sender_open_id: str = ""
    sender_display_name: str = ""


@dataclass(frozen=True, slots=True)
class TodoView:
    title: str
    deadline_text: str
    status: str


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    outcome: str
    affected_todos: dict[str, list[TodoView]] = field(default_factory=dict)
    resolved_task_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SecretaryResponse:
    text: str
    action: StructuredAction
    resolved_task_ids: list[str] = field(default_factory=list)


class ActionInterpreter(Protocol):
    async def interpret(
        self,
        message: IncomingMessage,
        context: dict[str, Any],
    ) -> StructuredAction: ...


class ActionExecutor(Protocol):
    async def execute(
        self,
        action: StructuredAction,
        message: IncomingMessage,
    ) -> ExecutionResult: ...


class SecretaryAgent:
    def __init__(
        self,
        interpreter: ActionInterpreter,
        executor: ActionExecutor,
    ) -> None:
        self._interpreter = interpreter
        self._executor = executor

    async def handle(
        self,
        message: IncomingMessage,
        *,
        context: dict[str, Any],
    ) -> SecretaryResponse:
        with language_scope(context.get("language", current_language())):
            return await self._handle(message, context=context)

    async def _handle(self, message, *, context):
        action = await self._interpreter.interpret(message, context)
        if action.action_type is ActionType.IGNORE:
            return SecretaryResponse(text="", action=action)
        if action.ambiguity is not None:
            field_description = {
                "project_id": t("属于哪个项目"),
                "task_id": t("指的是哪个任务"),
                "assignee_id": t("负责人是谁"),
            }.get(action.ambiguity.field, action.ambiguity.field)
            text = (
                t("我理解你要{understanding}。目前不能确定{field}，{question}",
                  understanding=action.understanding, field=field_description,
                  question=action.ambiguity.question)
            )
            return SecretaryResponse(text=text, action=action)

        result = await self._executor.execute(action, message)
        parts = [
            result.outcome,
            t("我理解并执行的是：\n{understanding}。", understanding=action.understanding),
        ]
        for assignee, todos in result.affected_todos.items():
            lines = [
                f"{index}. {todo.title}｜{todo.deadline_text}｜{todo.status}"
                for index, todo in enumerate(todos, start=1)
            ]
            parts.append(t("{assignee}当前任务：\n", assignee=assignee) + "\n".join(lines))
        return SecretaryResponse(text="\n\n".join(parts), action=action, resolved_task_ids=result.resolved_task_ids)
