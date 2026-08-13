from app.config import Settings


def test_csv_and_json_environment_settings(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://one.example,https://two.example")
    monkeypatch.setenv("ENABLED_CHANNELS", "shopee,qoo10")
    monkeypatch.setenv("IMAGE_HOST_ALLOWLIST", "cdn.example.com,images.example.com")
    monkeypatch.setenv(
        "SHOPEE_LOGISTIC_INFO",
        '[{"enabled":true,"logistic_id":123456}]',
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["https://one.example", "https://two.example"]
    assert settings.enabled_channels == ["shopee", "qoo10"]
    assert settings.image_host_allowlist == ["cdn.example.com", "images.example.com"]
    assert settings.shopee_logistic_info == [
        {"enabled": True, "logistic_id": 123456}
    ]
