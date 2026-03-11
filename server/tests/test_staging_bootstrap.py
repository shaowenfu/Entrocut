from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app, settings


def _configure_staging_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "staging")
    monkeypatch.setattr(settings, "staging_test_bootstrap_enabled", True)
    monkeypatch.setattr(settings, "staging_test_bootstrap_secret", "staging-bootstrap-secret")
    monkeypatch.setattr(settings, "auth_google_client_id", "test-google-client-id")
    monkeypatch.setattr(settings, "auth_google_client_secret", "test-google-client-secret")
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(settings, "allow_inmemory_mongo_fallback", True)
    monkeypatch.setattr(settings, "allow_inmemory_redis_fallback", True)


def test_staging_bootstrap_is_hidden_outside_staging(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(settings, "staging_test_bootstrap_enabled", False)
    client = TestClient(app)

    response = client.post(
        "/api/v1/test/bootstrap/login-session",
        headers={"X-Bootstrap-Secret": "irrelevant"},
        json={"login_session_id": "login_test_001", "provider": "google"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_staging_bootstrap_requires_secret(monkeypatch) -> None:
    _configure_staging_runtime(monkeypatch)
    client = TestClient(app)
    create_response = client.post(
        "/api/v1/auth/login-sessions",
        json={"provider": "google", "client_redirect_uri": "http://127.0.0.1:5173/"},
    )
    assert create_response.status_code == 200

    response = client.post(
        "/api/v1/test/bootstrap/login-session",
        headers={"X-Bootstrap-Secret": "wrong-secret"},
        json={"login_session_id": create_response.json()["login_session_id"], "provider": "google"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_INVALID"


def test_staging_bootstrap_authenticates_login_session(monkeypatch) -> None:
    _configure_staging_runtime(monkeypatch)
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/auth/login-sessions",
        json={"provider": "google", "client_redirect_uri": "http://127.0.0.1:5173/"},
    )
    assert create_response.status_code == 200
    login_session_id = create_response.json()["login_session_id"]

    bootstrap_response = client.post(
        "/api/v1/test/bootstrap/login-session",
        headers={"X-Bootstrap-Secret": "staging-bootstrap-secret"},
        json={"login_session_id": login_session_id, "provider": "google"},
    )
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json()["status"] == "authenticated"

    claim_response = client.get(f"/api/v1/auth/login-sessions/{login_session_id}")
    assert claim_response.status_code == 200
    body = claim_response.json()
    assert body["status"] == "consumed"
    assert body["result"]["access_token"]
    assert body["result"]["refresh_token"]
