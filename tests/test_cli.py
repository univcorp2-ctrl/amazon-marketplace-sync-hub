import asyncio
from pathlib import Path

from app import cli
from app.config import Settings


def test_production_sync_fails_closed_without_persisted_listing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    settings = Settings(
        app_mode="production",
        api_live_enabled=True,
        database_url=f"sqlite:///{tmp_path / 'empty.db'}",
        cors_origins=["https://marketplace-sync-ops.pages.dev"],
        enabled_channels=["shopee"],
        amazon_lwa_client_id="client",
        amazon_lwa_client_secret="secret",
        amazon_refresh_token="refresh",
        shopee_partner_id=1,
        shopee_partner_key="partner-key",
        shopee_shop_id=2,
        shopee_access_token="access",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    exit_code = asyncio.run(cli.run(cli.parser().parse_args(["sync"])))

    assert exit_code == 4
    assert "No persisted listings" in capsys.readouterr().out
