from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_language: Literal["zh-CN", "en-US"] = "zh-CN"
    app_timezone: str = "UTC"
    database_url: str = "postgresql+asyncpg://huiyang:huiyang@db:5432/huiyang"
    admin_feishu_user_id: str = ""
    llm_provider: Literal["openai_compatible", "deepseek"] = "openai_compatible"
    llm_api_base_url: str = ""
    llm_api_key: str = Field(default="", repr=False)
    llm_model: str = ""
    platform_enabled: bool = False
    team_web_enabled: bool = False
    team_public_url: str = ""
    team_static_dir: str = "/root/huiyang/web/dist"
    feishu_event_mode: Literal["long_connection"] = "long_connection"
    feishu_app_id: str = ""
    feishu_app_secret: str = Field(default="", repr=False)
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    overdue_reminder_policy: str = "disabled"
    env_path: str = "/root/huiyang/.env"

    def validate_feishu(self):
        if not self.feishu_app_id or not self.feishu_app_secret:
            raise ValueError("FEISHU_APP_ID / FEISHU_APP_SECRET are required")

    def validate_live(self):
        from zoneinfo import ZoneInfo
        ZoneInfo(self.app_timezone)
        self.validate_feishu()
        if not self.llm_api_key or not self.llm_api_base_url or not self.llm_model:
            raise ValueError("LLM_API_KEY / LLM_API_BASE_URL / LLM_MODEL are required")
        if not self.llm_api_base_url.startswith("https://"):
            raise ValueError("LLM_API_BASE_URL must use HTTPS")
        if self.overdue_reminder_policy != "disabled":
            raise ValueError("Only disabled overdue notifications are implemented")
