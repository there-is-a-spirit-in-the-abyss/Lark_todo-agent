import json
from datetime import UTC, datetime

import httpx
import pytest

from huiyang.adapters.events import normalize_event
from huiyang.adapters.feishu_api import FeishuAPIAdapter, FeishuAPIError, delivery_key
from huiyang.agent.structured_llm import ActionDocument, ModelOutputError, StructuredLLMAdapter
from huiyang.services.secretary import IncomingMessage


def event(text="你好", *, user_id="u_real", event_id="evt-1", chat_type="group"):
    return {
        "header": {"event_type": "im.message.receive_v1", "event_id": event_id},
        "event": {
            "sender": {"sender_type": "user", "sender_id": {"user_id": user_id, "open_id": "ou_person"}},
            "message": {"message_id": "msg-" + event_id, "chat_id": "oc_group", "chat_type": chat_type,
                        "message_type": "text", "content": json.dumps({"text": text}),
                        "mentions": [{"key": "@_user_1", "id": {"open_id": "ou_bot"}, "name": "秘书"}]},
        },
    }


def test_real_user_id_is_required_and_bot_mentions_are_resolved():
    actual = normalize_event(event("@_user_1 我的任务"), bot_open_id="ou_bot")
    assert actual.message.sender_id == "u_real"
    assert actual.message.sender_open_id == "ou_person"
    assert actual.message.mentioned_bot
    assert actual.message.text == "@机器人 我的任务"
    with pytest.raises(ValueError, match="employee_id"):
        normalize_event(event(user_id=""))
    assert not normalize_event(event(), bot_open_id="another_bot").message.mentioned_bot


def document(**changes):
    data = {key: None for key in ActionDocument.model_fields}
    data.update(action_type="ignore", understanding="", update_fields=[])
    return data | changes


@pytest.mark.asyncio
async def test_strict_model_schema_ignore_and_rejection():
    requests = []
    async def transport(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps(document())},
        }]})
    client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    adapter = StructuredLLMAdapter(api_key="test-secret", base_url="https://llm.test/v1", model="test", client=client)
    msg = IncomingMessage("u", "chat", "group", "午饭吃什么", datetime.now(UTC))
    action = await adapter.interpret(msg, {})
    assert action.action_type.value == "ignore"
    schema = requests[0]["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["required"]) == set(schema["schema"]["properties"])
    assert requests[0]["model"] == "test"
    await adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", [
    {"finish_reason": "length", "message": {"content": "{}"}},
    {"finish_reason": "stop", "message": {"content": "not json"}},
    {"finish_reason": "stop", "message": {"refusal": "no"}},
    {"finish_reason": "stop", "message": {"content": json.dumps(document(action_type="delete_task"))}},
])
async def test_invalid_model_output_never_becomes_an_action(choice):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"choices": [choice]})))
    adapter = StructuredLLMAdapter(api_key="hidden", base_url="https://llm.test/v1", model="test", client=client)
    with pytest.raises(ModelOutputError):
        await adapter.interpret(IncomingMessage("u", "c", "p2p", "删除", datetime.now(UTC)), {})
    await adapter.close()


@pytest.mark.asyncio
async def test_feishu_token_cache_send_types_mentions_and_idempotency():
    calls = []
    def transport(request):
        calls.append(request)
        if "tenant_access_token" in request.url.path:
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token", "expire": 7200})
        return httpx.Response(200, json={"code": 0})
    api = FeishuAPIAdapter("app", "secret", client=httpx.AsyncClient(base_url="https://open.feishu.cn", transport=httpx.MockTransport(transport)))
    token = delivery_key.set("event-1")
    try:
        await api.send_private("u_real", "hello")
        await api.send_group("oc_group", "提醒", mention_user_id="u_real")
    finally:
        delivery_key.reset(token)
    assert len(calls) == 3
    assert calls[1].url.params["receive_id_type"] == "user_id"
    assert calls[2].url.params["receive_id_type"] == "chat_id"
    body = json.loads(calls[2].content)
    assert '<at user_id="u_real">' in json.loads(body["content"])["text"]
    assert body["uuid"]
    await api.close()
