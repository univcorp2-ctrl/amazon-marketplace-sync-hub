from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_demo_fetch_listing_and_duplicate_guard(tmp_path: Path) -> None:
    settings = Settings(
        app_mode="demo",
        api_live_enabled=False,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        enabled_channels=["shopee", "qoo10"],
        shopee_default_category_id=100,
        qoo10_default_category_id="200",
        qoo10_shipping_no=1,
    )
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["amazon_source"] == "SP-API"
        fetched = client.post("/api/products/B0DEMO1234/fetch")
        assert fetched.status_code == 200
        assert fetched.json()["price"] == 3980

        blocked = client.post(
            "/api/listings",
            json={
                "asin": "B0DEMO1234",
                "channels": ["shopee"],
                "rights_confirmed": False,
            },
        )
        assert blocked.status_code == 403
        payload = {
            "asin": "B0DEMO1234",
            "channels": ["shopee", "qoo10"],
            "rights_confirmed": True,
        }
        listed = client.post("/api/listings", json=payload)
        assert listed.status_code == 200
        assert len(listed.json()["results"]) == 2
        assert len(client.get("/api/listings").json()) == 2
        duplicate = client.post("/api/listings", json=payload)
        assert duplicate.status_code == 409


def test_production_routes_require_token(tmp_path: Path) -> None:
    settings = Settings(
        app_mode="production",
        api_live_enabled=True,
        app_api_token="correct-horse-battery-staple-0123456789",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["https://dashboard.example.com"],
        enabled_channels=["shopee"],
        amazon_lwa_client_id="client",
        amazon_lwa_client_secret="secret",
        amazon_refresh_token="refresh",
        shopee_partner_id=1,
        shopee_partner_key="partner-key",
        shopee_shop_id=2,
        shopee_access_token="access",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/products").status_code == 401
        response = client.get(
            "/api/products",
            headers={"Authorization": "Bearer correct-horse-battery-staple-0123456789"},
        )
        assert response.status_code == 200
        assert response.json() == []
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ready"
        assert health.json()["missing_config"] == []


def test_invalid_asin(tmp_path: Path) -> None:
    settings = Settings(
        app_mode="demo", database_url=f"sqlite:///{tmp_path / 'test.db'}"
    )
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/products/invalid/fetch")
        assert response.status_code == 400
