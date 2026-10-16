import pytest

from huiyang.agent.structured_llm import StructuredLLMAdapter
from huiyang.adapters.feishu_api import FeishuAPIAdapter


@pytest.mark.asyncio
async def test_platform_clients_can_start_with_host_socks_proxy(monkeypatch):
    # No network request: constructor must support the server's existing proxy.
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")
    monkeypatch.setenv("all_proxy", "socks5://127.0.0.1:1080")
    llm = StructuredLLMAdapter(api_key="test", base_url="https://example.invalid/v1", model="test")
    feishu = FeishuAPIAdapter("test", "test")
    await llm.close()
    await feishu.close()
