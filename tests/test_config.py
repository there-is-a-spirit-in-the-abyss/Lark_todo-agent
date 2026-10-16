from importlib import import_module

import pytest


def load_config():
    try:
        return import_module("huiyang.config")
    except ModuleNotFoundError:
        pytest.fail("application config is missing")


def test_settings_read_secrets_and_runtime_values_from_environment(monkeypatch) -> None:
    config = load_config()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example/db")
    monkeypatch.setenv("ADMIN_FEISHU_USER_ID", "ou_admin")
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Shanghai")

    settings = config.Settings(_env_file=None)

    assert settings.database_url == "postgresql+asyncpg://example/db"
    assert settings.admin_feishu_user_id == "ou_admin"
    assert settings.app_timezone == "Asia/Shanghai"
    assert settings.overdue_reminder_policy == "disabled"
