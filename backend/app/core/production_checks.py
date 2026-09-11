"""Production configuration advisories (non-blocking).

These helpers never prevent process startup. Use them in smoke / deploy checks.
"""

from __future__ import annotations

from app.core.config import Settings


def production_config_warnings(settings: Settings) -> list[str]:
    """Return human-readable production hygiene warnings (empty when OK)."""
    warnings: list[str] = []
    env = (settings.app_env or "").strip().lower()
    if env != "production":
        return warnings

    if not settings.auth_cookie_secure:
        warnings.append(
            "AUTH_COOKIE_SECURE=false while APP_ENV=production "
            "(set true for HTTPS; keep false only for trusted LAN HTTP)."
        )
    if "localhost" in settings.cors_origins.lower() or "127.0.0.1" in settings.cors_origins:
        warnings.append(
            "CORS_ORIGINS still references localhost/127.0.0.1 in production."
        )
    # Embedding dimension / API URL are hard-validated in Settings when enabled;
    # do not duplicate those as soft warnings here.
    return warnings
