"""Local administration; never prints platform or database secrets."""
import argparse
import asyncio
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values, set_key
from sqlalchemy import select

from huiyang.config import Settings
from huiyang.database import Database
from huiyang.domain.platform import ChatObservation, FeishuInbox
from huiyang.domain.persistence import User
from huiyang.services.enrollment import effective_admin


def prepare_env():
    root = Path.cwd().resolve()
    if str(root) != "/root/huiyang":
        raise SystemExit("Run from /root/huiyang")
    path = root / ".env"
    if not path.exists():
        path.touch(mode=0o600)
    existing = dotenv_values(path)
    values = {
        "PLATFORM_ENABLED": "true", "FEISHU_EVENT_MODE": "long_connection",
        "APP_TIMEZONE": "UTC",
        "FEISHU_APP_ID": "", "FEISHU_APP_SECRET": "",
        "LLM_PROVIDER": "openai_compatible", "LLM_API_BASE_URL": "",
        "LLM_API_KEY": "", "LLM_MODEL": "",
        "OVERDUE_REMINDER_POLICY": "disabled",
    }
    for key, value in values.items():
        if key not in existing:
            set_key(str(path), key, value, quote_mode="always")
    if not existing.get("POSTGRES_PASSWORD"):
        set_key(str(path), "POSTGRES_PASSWORD", secrets.token_hex(24), quote_mode="never")
    path.chmod(0o600)
    print("Prepared /root/huiyang/.env; existing values preserved; secrets not displayed.")


async def run(command):
    settings = Settings()
    if command == "check":
        flags = {
            "FEISHU_APP_ID": bool(settings.feishu_app_id),
            "FEISHU_APP_SECRET": bool(settings.feishu_app_secret),
            "LLM_PROVIDER": settings.llm_provider,
            "LLM_API_BASE_URL": bool(settings.llm_api_base_url),
            "LLM_API_KEY": bool(settings.llm_api_key),
            "LLM_MODEL": bool(settings.llm_model),
            "ADMIN_DISCOVERY": "automatic from first group owner; PostgreSQL binding; no manual ID required",
        }
        for key, value in flags.items():
            print(f"{key}: {value}")
        return
    if command == "probe-llm":
        from datetime import UTC, datetime
        from huiyang.agent.structured_llm import StructuredLLMAdapter
        from huiyang.services.secretary import IncomingMessage
        adapter_type = StructuredLLMAdapter
        if settings.llm_provider == "deepseek":
            from huiyang.agent.deepseek_llm import DeepSeekLLMAdapter
            adapter_type = DeepSeekLLMAdapter
        adapter = adapter_type(api_key=settings.llm_api_key,
            base_url=settings.llm_api_base_url, model=settings.llm_model)
        try:
            result = await adapter.interpret(
                IncomingMessage("schema_probe", "local_probe", "p2p", "查看我的任务", datetime.now(UTC)),
                {"timezone": settings.app_timezone, "users": [], "projects": [], "tasks": []},
            )
            print("Strict schema response validated:", result.action_type.value)
        finally:
            await adapter.close()
        return
    database = Database(settings)
    try:
        async with database.session_factory() as session:
            if command == "admin-status":
                print("Administrator bound:", bool(await effective_admin(session)))
            elif command == "discovered":
                for user in await session.scalars(select(User)):
                    print("member", user.feishu_user_id, user.display_name)
                for chat_id in await session.scalars(select(ChatObservation.chat_id).where(
                    ChatObservation.chat_type == "group").distinct()):
                    print("group", chat_id)
            elif command == "status":
                for row in await session.scalars(select(FeishuInbox).where(FeishuInbox.state != "done")):
                    print(row.event_id, row.state, row.attempts, row.error_code)
            elif command == "retry-failed":
                for row in await session.scalars(select(FeishuInbox).where(FeishuInbox.state == "failed")):
                    row.state = "ready" if row.response else "pending"
                    row.retry_at = None
                    row.attempts = 0
                await session.commit()
                print("Failed events queued for retry.")
    finally:
        await database.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare-env", "check", "admin-status", "discovered", "status", "retry-failed", "probe-llm"])
    args = parser.parse_args()
    if args.command == "prepare-env":
        prepare_env()
    else:
        try:
            asyncio.run(run(args.command))
        except Exception as error:
            # Avoid echoing exception bodies containing HTTP credentials or DB URLs.
            raise SystemExit(f"Command failed: {type(error).__name__}; check configuration and service status.") from None


if __name__ == "__main__":
    main()
