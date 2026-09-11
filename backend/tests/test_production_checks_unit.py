"""Unit tests for production config advisories."""

from app.core.config import Settings
from app.core.production_checks import production_config_warnings


def test_production_warnings_empty_in_development() -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "AUTH_COOKIE_SECURE": False,
            "CORS_ORIGINS": "http://localhost:5173",
        }
    )
    assert production_config_warnings(settings) == []


def test_production_warnings_for_insecure_cookie_and_localhost_cors() -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "AUTH_COOKIE_SECURE": False,
            "CORS_ORIGINS": "http://localhost:8080",
            "EMBEDDING_ENABLED": False,
        }
    )
    warnings = production_config_warnings(settings)
    assert any("AUTH_COOKIE_SECURE" in w for w in warnings)
    assert any("CORS_ORIGINS" in w for w in warnings)


def test_production_ok_when_hardened() -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "AUTH_COOKIE_SECURE": True,
            "CORS_ORIGINS": "https://ideaflow.example",
            "EMBEDDING_ENABLED": False,
        }
    )
    assert production_config_warnings(settings) == []
