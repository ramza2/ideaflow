"""Health API tests."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import reset_engine
from app.main import app

client = TestClient(app)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def test_health_returns_ok() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ideaflow-backend"
    assert body["version"] == "0.1.0"


def test_health_ready_returns_ready_when_db_available() -> None:
    mock_conn = MagicMock()
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    with patch("app.api.health.get_engine", return_value=mock_engine):
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ready", "service": "ideaflow-backend"}
    mock_conn.execute.assert_called_once()


def test_health_ready_returns_503_when_db_unavailable() -> None:
    with patch("app.api.health.get_engine", side_effect=Exception("connection failed")):
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "not_ready", "service": "ideaflow-backend"}
    assert "connection" not in str(body).lower()
    assert "password" not in str(body).lower()
    assert "database_url" not in str(body).lower()


@pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping health readiness integration test",
)
def test_health_ready_returns_ready_with_configured_postgresql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    get_settings.cache_clear()
    reset_engine()
    try:
        with TestClient(app) as integration_client:
            response = integration_client.get("/api/v1/health/ready")
    finally:
        reset_engine()
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "ideaflow-backend"}
