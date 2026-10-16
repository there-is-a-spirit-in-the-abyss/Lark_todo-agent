import json
from datetime import UTC, datetime

import httpx
import pytest

from huiyang.agent.structured_llm import ModelOutputError
from huiyang.services.secretary import IncomingMessage
from test_platform_adapters import document


def wire_document(**overrides):
    data = document()
    data.update(ambiguity={"field": None, "question": None},
                reminder_times=[], reminders_specified=False)
    data.update(overrides)
    return data


def response(data, status="completed"):
    return {"status": status, "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": json.dumps(data, ensure_ascii=False)}]}]}


def assert_supported_schema(node):
    if isinstance(node, list):
        for item in node:
            assert_supported_schema(item)
    elif isinstance(node, dict):
        assert "$ref" not in node
        assert "anyOf" not in node
        if isinstance(node.get("type"), list):
            assert not {"array", "object"} & set(node["type"])
            if "null" in node["type"] and "enum" in node:
                assert None in node["enum"]
        for value in node.values():
            assert_supported_schema(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("specified", [False, True])
async def test_responses_schema_preserves_absent_vs_explicit_empty_reminders(specified):
    from huiyang.agent.deepseek_llm import DeepSeekLLMAdapter
    def handle(request):
        body = json.loads(request.content)
        assert request.url.path == "/responses"
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["type"] == "json_schema"
        assert_supported_schema(body["text"]["format"]["schema"])
        return httpx.Response(200, json=response(wire_document(
            action_type="create_task", title="整理文档",
            reminders_specified=specified)))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    adapter = DeepSeekLLMAdapter(api_key="secret-test", base_url="https://example.invalid", model="test", client=client)
    action = await adapter.interpret(IncomingMessage("u", "c", "p2p", "记录任务", datetime.now(UTC)), {})
    assert action.payload["title"] == "整理文档"
    assert action.ambiguity is None
    assert ("reminder_times" in action.payload) is specified
    if specified:
        assert action.payload["reminder_times"] == []
    await adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("data,status", [
    (wire_document(), "incomplete"),
    (wire_document(ambiguity={"field": None, "question": "哪个项目？"}), "completed"),
    (wire_document(reminders_specified=False, reminder_times=["2030-01-01T00:00:00+00:00"]), "completed"),
    (wire_document(title=5), "completed"),
    (wire_document(action_type="update_task", task_id="00000000-0000-0000-0000-000000000001",
                   update_fields=["reminder_times"]), "completed"),
    (wire_document(action_type="update_task", task_id="00000000-0000-0000-0000-000000000001",
                   reminders_specified=True), "completed"),
])
async def test_responses_rejects_incomplete_or_inconsistent_action(data, status):
    from huiyang.agent.deepseek_llm import DeepSeekLLMAdapter
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response(data, status))))
    adapter = DeepSeekLLMAdapter(api_key="secret-test", base_url="https://example.invalid", model="test", client=client)
    with pytest.raises(ModelOutputError):
        await adapter.interpret(IncomingMessage("u", "c", "p2p", "任务", datetime.now(UTC)), {})
    await adapter.close()
