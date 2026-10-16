"""DeepSeek Responses wire format; canonical business actions remain unchanged."""
from huiyang.i18n import reply_language_prompt
import json

from pydantic import BaseModel, ConfigDict, StrictBool

from huiyang.agent.structured_llm import (
    ActionDocument, ModelOutputError, StructuredLLMAdapter, SYSTEM_PROMPT,
)


class WireAmbiguity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str | None
    question: str | None


class DeepSeekDocument(ActionDocument):
    ambiguity: WireAmbiguity
    reminder_times: list[str]
    reminders_specified: StrictBool

    def to_action(self):
        data = self.model_dump()
        specified = data.pop("reminders_specified")
        if self.action_type == "update_task":
            listed = "reminder_times" in self.update_fields
            if specified != listed:
                raise ValueError("Reminder update selection is inconsistent")
        if not specified:
            if data["reminder_times"]:
                raise ValueError("Inconsistent reminder selection")
            data["reminder_times"] = None
        ambiguity = data["ambiguity"]
        if ambiguity["field"] is None and ambiguity["question"] is None:
            data["ambiguity"] = None
        elif not ambiguity["field"] or not ambiguity["question"]:
            raise ValueError("Incomplete ambiguity")
        return ActionDocument.model_validate(data).to_action()


def response_schema():
    root = DeepSeekDocument.model_json_schema()

    def convert(node):
        if isinstance(node, list):
            return [convert(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return convert(root["$defs"][node["$ref"].split("/")[-1]])
        result = {key: convert(value) for key, value in node.items() if key != "$defs"}
        if "anyOf" in result:
            options = result.pop("anyOf")
            values = [item for item in options if item.get("type") != "null"]
            if len(values) != 1 or len(options) != 2:
                raise ValueError("Unsupported wire schema union")
            result.update(values[0])
            if result["type"] in {"array", "object"}:
                raise ValueError("Nullable containers require explicit wire representation")
            result["type"] = [result["type"], "null"]
            if "enum" in result:
                result["enum"] = [*result["enum"], None]
        return result

    return convert(root)


class DeepSeekLLMAdapter(StructuredLLMAdapter):
    def __init__(self, *, api_key, base_url, model, client=None):
        super().__init__(api_key=api_key, base_url=base_url, model=model, client=client)
        self.url = base_url.rstrip("/") + "/responses"

    async def interpret(self, message, context):
        wire_prompt = (
            "\n传输表示：无歧义时 ambiguity 的 field、question 都为 null。"
            "用户未显式指定提醒时 reminders_specified=false、reminder_times=[]；"
            "明确指定提醒时 reminders_specified=true，数组是指定时间；明确取消提醒用 true 和空数组。"
            "修改任务时 reminders_specified 必须与 update_fields 是否包含 reminder_times 一致。"
            "这些传输字段不改变业务规则。"
        )
        request = {
            "model": self.model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT + wire_prompt + reply_language_prompt(context)},
                {"role": "user", "content": json.dumps({
                    "sender_id": message.sender_id, "chat_type": message.chat_type,
                    "text": message.text, "mentioned_bot": message.mentioned_bot,
                    "current_time": message.received_at.isoformat(), "context": context,
                }, ensure_ascii=False, default=str)},
            ],
            "text": {"format": {"type": "json_schema", "name": "secretary_action",
                                "strict": True, "schema": response_schema()}},
        }
        try:
            response = await self.client.post(self.url, json=request,
                headers={"Authorization": f"Bearer {self.key}"})
            if response.status_code != 200:
                raise ModelOutputError(f"LLM HTTP {response.status_code}")
            data = response.json()
            if data.get("status") != "completed" or data.get("error"):
                raise ModelOutputError("LLM response not completed")
            texts = []
            for item in data["output"]:
                if item.get("type") == "reasoning":
                    continue
                if item.get("type") != "message" or item.get("role") != "assistant":
                    raise ModelOutputError("Unexpected LLM output")
                for part in item["content"]:
                    if part.get("type") != "output_text":
                        raise ModelOutputError("LLM refusal or unsupported content")
                    texts.append(part["text"])
            if len(texts) != 1:
                raise ModelOutputError("Expected exactly one Structured Action")
            return DeepSeekDocument.model_validate_json(texts[0]).to_action()
        except (KeyError, IndexError, TypeError, ValueError) as error:
            if isinstance(error, ModelOutputError):
                raise
            raise ModelOutputError("Invalid Structured Action output") from None
