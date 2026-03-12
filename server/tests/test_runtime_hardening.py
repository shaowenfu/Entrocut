from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.errors import ServerApiError
from app.main import app, metrics, rate_limit_service, settings
from app.runtime_guard import validate_runtime_settings


def _configure_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(settings, "allow_inmemory_mongo_fallback", True)
    monkeypatch.setattr(settings, "allow_inmemory_redis_fallback", True)
    monkeypatch.setattr(settings, "observability_enable_metrics", True)
    monkeypatch.setattr(settings, "auth_dev_fallback_enabled", True)
    rate_limit_service._memory_counters.clear()
    rate_limit_service._redis = None
    rate_limit_service._redis_ready = None


def test_validate_runtime_settings_rejects_production_defaults() -> None:
    prod_settings = Settings(
        app_env="production",
        mongodb_uri="mongodb+srv://example.mongodb.net/test",
        redis_url="redis://127.0.0.1:6379/0",
        allow_inmemory_mongo_fallback=False,
        allow_inmemory_redis_fallback=False,
        cors_allow_origins="https://app.entrocut.com",
        auth_dev_fallback_enabled=False,
        auth_jwt_secret="entrocut-dev-secret-change-me",
    )

    with pytest.raises(ServerApiError) as exc_info:
        validate_runtime_settings(prod_settings)

    assert exc_info.value.code == "DEPENDENCY_UNAVAILABLE"
    assert "AUTH_JWT_SECRET" in exc_info.value.message


def test_validate_runtime_settings_accepts_strict_configuration() -> None:
    prod_settings = Settings(
        app_env="production",
        mongodb_uri="mongodb+srv://example.mongodb.net/test",
        redis_url="redis://redis.internal:6379/0",
        allow_inmemory_mongo_fallback=False,
        allow_inmemory_redis_fallback=False,
        cors_allow_origins="https://app.entrocut.com",
        auth_dev_fallback_enabled=False,
        auth_jwt_secret="super-secret-production-key",
    )

    validate_runtime_settings(prod_settings)


def test_validate_runtime_settings_accepts_localhost_in_staging() -> None:
    staging_settings = Settings(
        app_env="staging",
        mongodb_uri="mongodb+srv://example.mongodb.net/test",
        redis_url="redis://redis.internal:6379/0",
        allow_inmemory_mongo_fallback=False,
        allow_inmemory_redis_fallback=False,
        cors_allow_origins="https://entrocut.sherwenfu.com,http://localhost:5173",
        auth_dev_fallback_enabled=False,
        auth_jwt_secret="super-secret-staging-key",
    )

    validate_runtime_settings(staging_settings)


def test_validate_runtime_settings_rejects_localhost_in_production() -> None:
    prod_settings = Settings(
        app_env="production",
        mongodb_uri="mongodb+srv://example.mongodb.net/test",
        redis_url="redis://redis.internal:6379/0",
        allow_inmemory_mongo_fallback=False,
        allow_inmemory_redis_fallback=False,
        cors_allow_origins="https://entrocut.sherwenfu.com,http://localhost:5173",
        auth_dev_fallback_enabled=False,
        auth_jwt_secret="super-secret-production-key",
    )

    with pytest.raises(ServerApiError) as exc_info:
        validate_runtime_settings(prod_settings)

    assert exc_info.value.code == "DEPENDENCY_UNAVAILABLE"
    assert "localhost entries in production" in exc_info.value.message


def test_readyz_reports_local_fallback_dependencies(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    client = TestClient(app)

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["dependencies"]["mongodb"]["mode"] == "in_memory"
    assert body["dependencies"]["redis"]["mode"] == "in_memory"


def test_metrics_endpoint_exposes_http_and_dependency_metrics(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    client = TestClient(app)

    metrics.inc("server_http_requests_total", route="/test", method="GET", status_code="200")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "server_http_requests_total" in response.text
    assert "server_dependency_health" in response.text


def test_metrics_endpoint_can_be_disabled(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    monkeypatch.setattr(settings, "observability_enable_metrics", False)
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
