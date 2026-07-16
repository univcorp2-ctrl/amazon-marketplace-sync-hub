from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_demo_fetch_and_listing(tmp_path: Path) -> None:
    settings = Settings(
        app_mode="demo",
        api_live_enabled=False,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
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
            json={"asin": "B0DEMO1234", "channels": ["shopee"], "rights_confirmed": False},
        )
        assert blocked.status_code == 403

        listed = client.post(
            "/api/listings",
            json={
                "asin": "B0DEMO1234",
                "channels": ["shopee", "qoo10"],
                "rights_confirmed": True,
            },
        )
        assert listed.status_code == 200
        assert len(listed.json()["results"]) == 2
        assert len(client.get("/api/listings").json()) == 2


def test_invalid_asin(tmp_path: Path) -> None:
    settings = Settings(app_mode="demo", database_url=f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/products/invalid/fetch")
        assert response.status_code == 400
