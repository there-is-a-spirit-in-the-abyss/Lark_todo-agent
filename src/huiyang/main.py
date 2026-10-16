from __future__ import annotations

from typing import Any, Protocol

from fastapi import FastAPI, HTTPException
from huiyang.config import Settings
from huiyang.lifecycle import live_lifespan


class WebhookGateway(Protocol):
    async def process(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def create_app(*, feishu_gateway: WebhookGateway | None = None, settings=None, team_dependencies=None) -> FastAPI:
    settings = settings or Settings()
    lifespan = (live_lifespan(settings)
                if settings.platform_enabled and feishu_gateway is None else None)
    application = FastAPI(title="Huiyang Todo Secretary", lifespan=lifespan)
    if settings.team_web_enabled:
        from huiyang.team.api import setup_team
        application.router.lifespan_context = setup_team(application, settings, lifespan, team_dependencies)
    application.state.feishu_gateway = feishu_gateway

    @application.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/webhooks/feishu", tags=["feishu"])
    async def feishu_webhook(payload: dict[str, Any]) -> dict[str, Any]:
        gateway = application.state.feishu_gateway
        if gateway is None:
            raise HTTPException(
                status_code=503,
                detail="Feishu gateway is not configured",
            )
        try:
            return await gateway.process(payload)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return application


app = create_app()
