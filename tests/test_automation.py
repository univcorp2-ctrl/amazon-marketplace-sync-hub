from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def settings_for(tmp_path: Path, **overrides):
    values = dict(app_mode="demo", api_live_enabled=False, database_url=f"sqlite:///{tmp_path / 'test.db'}", shopee_default_category_id=100, shopee_logistic_info=[{"logistic_id": 1, "enabled": True}], shopee_market="SG")
    values.update(overrides)
    return Settings(**values)


def test_bulk_preview_is_non_consequential(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        response = client.post("/api/automation/shopee", json={"query": "stationery", "max_items": 5})
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "preview"
        assert body["would_list"] == 1
        assert client.get("/api/listings").json() == []


def test_bulk_execute_requires_enable_gate(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        response = client.post("/api/automation/shopee", json={"query": "stationery", "execute": True, "rights_confirmed": True})
        assert response.status_code == 403
        assert "Bulk listing is disabled" in response.json()["detail"]


def test_bulk_execute_demo_with_gate(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path, bulk_listing_enabled=True))) as client:
        response = client.post("/api/automation/shopee", json={"query": "stationery", "execute": True, "rights_confirmed": True})
        assert response.status_code == 200
        assert len(response.json()["listed"]) == 1
