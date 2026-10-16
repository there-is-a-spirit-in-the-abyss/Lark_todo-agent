import pytest
from httpx import ASGITransport, AsyncClient

from huiyang.main import create_app


class FakeGateway:
    def __init__(self) -> None:
        self.payloads = []

    async def process(self, payload):
        self.payloads.append(payload)
        return {"code": 0}


@pytest.mark.asyncio
async def test_webhook_endpoint_delegates_to_gateway() -> None:
    gateway = FakeGateway()
    app = create_app(feishu_gateway=gateway)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/webhooks/feishu",
            json={"header": {"event_id": "event-1"}},
        )

    assert response.status_code == 200
    assert response.json() == {"code": 0}
    assert gateway.payloads == [{"header": {"event_id": "event-1"}}]
