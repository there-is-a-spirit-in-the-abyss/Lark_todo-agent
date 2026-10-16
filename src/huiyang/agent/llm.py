from collections import deque
from typing import Any, Protocol

from huiyang.agent.schemas import StructuredAction
from huiyang.services.secretary import IncomingMessage


class LLMAdapter(Protocol):
    async def interpret(
        self,
        message: IncomingMessage,
        context: dict[str, Any],
    ) -> StructuredAction: ...


class FakeLLMAdapter:
    def __init__(self, actions: list[StructuredAction]) -> None:
        self._actions = deque(actions)
        self.calls: list[tuple[IncomingMessage, dict[str, Any]]] = []

    async def interpret(
        self,
        message: IncomingMessage,
        context: dict[str, Any],
    ) -> StructuredAction:
        self.calls.append((message, context))
        if not self._actions:
            raise RuntimeError("No scripted StructuredAction remains")
        return self._actions.popleft()
