from importlib import import_module

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_reports_service_ready() -> None:
    try:
        module = import_module("huiyang.main")
    except ModuleNotFoundError:
        pytest.fail("huiyang.main is missing")

    app = getattr(module, "app", None)
    assert app is not None, "FastAPI app is missing"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
