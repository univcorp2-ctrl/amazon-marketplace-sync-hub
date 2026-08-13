import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.connectors.shopee import ShopeeClient


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class TokenClient:
    def __init__(self) -> None:
        self.refresh_calls = 0

    async def post(self, *_: Any, **__: Any) -> FakeResponse:
        self.refresh_calls += 1
        await asyncio.sleep(0.01)
        return FakeResponse(
            {
                "response": {
                    "access_token": "rotated-access-token",
                    "refresh_token": "rotated-refresh-token",
                    "expire_in": 14400,
                }
            }
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_concurrent_refresh_consumes_refresh_token_once(tmp_path: Path) -> None:
    state_file = tmp_path / "shopee-token-state.json"
    settings = Settings(
        app_mode="test",
        shopee_partner_id=10,
        shopee_partner_key="partner-key",
        shopee_shop_id=20,
        shopee_refresh_token="initial-refresh-token",
        shopee_token_state_file=str(state_file),
    )
    transport = TokenClient()
    client = ShopeeClient(settings, client=transport)  # type: ignore[arg-type]

    first, second = await asyncio.gather(
        client._ensure_access_token(), client._ensure_access_token()
    )

    assert first == second == "rotated-access-token"
    assert transport.refresh_calls == 1
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["refresh_token"] == "rotated-refresh-token"


@pytest.mark.parametrize(
    ("hostname", "allowed"),
    [
        ("cdn.example.com", True),
        ("assets.cdn.example.com", True),
        ("cdn.example.com.evil.test", False),
        ("127.0.0.1", False),
        ("localhost", False),
    ],
)
def test_production_image_host_allowlist(hostname: str, allowed: bool) -> None:
    settings = Settings(
        app_mode="production",
        image_host_allowlist=["cdn.example.com"],
    )
    client = ShopeeClient(settings, client=TokenClient())  # type: ignore[arg-type]

    assert client._image_host_allowed(hostname) is allowed
