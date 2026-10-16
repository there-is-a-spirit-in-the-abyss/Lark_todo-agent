import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from huiyang.adapters.long_connection import persist_event, sync_url
from huiyang.config import Settings
from huiyang.domain.models import Base
from huiyang.domain.platform import FeishuInbox
from test_platform_adapters import event


def test_official_sdk_dispatches_message_and_persists_before_callback_returns(tmp_path):
    import lark_oapi as lark
    engine = create_engine("sqlite:///" + str(tmp_path / "sdk.sqlite"))
    Base.metadata.create_all(engine)
    payload = event()
    payload["schema"] = "2.0"
    def callback(data):
        persist_event(engine, json.loads(lark.JSON.marshal(data)))
    dispatcher = lark.EventDispatcherHandler.builder("", "").register_p2_im_message_receive_v1(callback).build()
    dispatcher._do_without_validation(json.dumps(payload).encode())
    dispatcher._do_without_validation(json.dumps(payload).encode())
    with Session(engine) as session:
        rows = list(session.scalars(select(FeishuInbox)))
        assert len(rows) == 1
        assert rows[0].payload["event"]["sender"]["sender_id"]["user_id"] == "u_real"
    engine.dispose()


def test_sync_url_preserves_password_and_uses_psycopg():
    url = sync_url("postgresql+asyncpg://huiyang:p%40ss@db/huiyang")
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss"


def test_live_config_does_not_require_webhook_secrets_and_does_require_strict_provider():
    settings = Settings(_env_file=None, feishu_app_id="app", feishu_app_secret="secret",
        llm_api_key="secret", llm_model="model", llm_api_base_url="https://model.test/v1")
    settings.validate_live()
    assert settings.feishu_verification_token == ""
    assert settings.feishu_encrypt_key == ""
    assert settings.feishu_event_mode == "long_connection"
    assert "secret" not in repr(settings)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai_compatible", "deepseek"])
async def test_lifecycle_starts_and_stops_jobs_and_both_worker_tasks(monkeypatch, provider):
    from huiyang import lifecycle
    from huiyang.agent import deepseek_llm
    events = []
    class Database:
        def __init__(self, settings):
            self.session_factory = object()
        async def dispose(self):
            events.append("db_close")
    class API:
        def __init__(self, *args):
            pass
        async def bot_open_id(self):
            return "ou_bot"
        async def close(self):
            events.append("api_close")
    class LLM:
        def __init__(self, **kwargs):
            pass
        async def close(self):
            events.append("llm_close")
    class Scheduler:
        running = False
        def __init__(self, **kwargs):
            pass
        def add_job(self, *args, **kwargs):
            events.append("job")
        def start(self):
            self.running = True
            events.append("scheduler_start")
        def shutdown(self, **kwargs):
            self.running = False
            events.append("scheduler_stop")
    class Gateway:
        def __init__(self, *args, **kwargs):
            assert kwargs["bot_open_id"] == "ou_bot"
        async def run(self):
            await waiting("gateway")
    async def waiting(name):
        import asyncio
        events.append(name + "_start")
        try:
            await asyncio.Event().wait()
        finally:
            events.append(name + "_stop")
    async def receiver(app):
        await waiting("receiver")
    monkeypatch.setattr(lifecycle, "Database", Database)
    monkeypatch.setattr(lifecycle, "FeishuAPIAdapter", API)
    monkeypatch.setattr(lifecycle, "StructuredLLMAdapter", LLM)
    monkeypatch.setattr(deepseek_llm, "DeepSeekLLMAdapter", LLM)
    monkeypatch.setattr(lifecycle, "AsyncIOScheduler", Scheduler)
    monkeypatch.setattr(lifecycle, "PlatformGateway", Gateway)
    monkeypatch.setattr(lifecycle, "supervise_receiver", receiver)
    settings = Settings(_env_file=None, llm_provider=provider, feishu_app_id="app", feishu_app_secret="secret",
        llm_api_key="secret", llm_model="model", llm_api_base_url="https://model.test/v1")
    app = SimpleNamespace(state=SimpleNamespace())
    import asyncio
    async with lifecycle.live_lifespan(settings)(app):
        await asyncio.sleep(0)
        assert app.state.platform_running
    assert not app.state.platform_running
    assert events.count("job") == 2
    assert {"gateway_stop", "receiver_stop", "scheduler_stop", "db_close", "llm_close", "api_close"} <= set(events)
