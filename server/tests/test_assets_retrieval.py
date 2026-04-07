from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.auth import new_id
from app.shared.time import now_utc, to_iso
from app.core.errors import query_embedding_failed, retrieval_failed
from app.main import app, rate_limit_service, settings, store, token_service


def _configure_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    rate_limit_service._memory_counters.clear()
    rate_limit_service._redis = None
    rate_limit_service._redis_ready = None


def _create_user() -> dict[str, Any]:
    current_time = now_utc()
    user = {
        "_id": new_id("user"),
        "email": f"{new_id('mail')}@retrieval.local",
        "display_name": "Retrieval Test User",
        "avatar_url": None,
        "status": "active",
        "primary_provider": "google",
        "plan": "free",
        "quota_total": 10000,
        "quota_status": "healthy",
        "remaining_quota": 10000,
        "created_at": to_iso(current_time),
        "updated_at": to_iso(current_time),
        "last_login_at": to_iso(current_time),
    }
    store.mongo.create_user(user)
    return user


def test_retrieval_requires_bearer_token() -> None:
    client = TestClient(app)

    response = client.post("/v1/assets/retrieval", json={"query_text": "test"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"


def test_retrieval_validates_query_text(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    response = client.post(
        "/v1/assets/retrieval",
        headers={"Authorization": f"Bearer {bundle['access_token']}"},
        json={"query_text": "", "topk": 8},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_RETRIEVAL_REQUEST"


def test_retrieval_success(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    with patch("app.main.vector_service.retrieve") as mock_retrieve:
        mock_retrieve.return_value = {
            "collection_name": "test_collection",
            "partition": "default",
            "query": {
                "query_text": "滑雪跃起的动作",
                "topk": 8,
                "filter": "media_type = 'video'",
            },
            "matches": [
                {
                    "id": "asset_001",
                    "score": 0.95,
                    "fields": {"asset_id": "asset_001", "media_type": "video"},
                }
            ],
            "usage": {"embedding_query_count": 1, "dashvector_read_units": 1},
        }

        response = client.post(
            "/v1/assets/retrieval",
            headers={"Authorization": f"Bearer {bundle['access_token']}"},
            json={
                "collection_name": "test_collection",
                "query_text": "滑雪跃起的动作",
                "topk": 8,
                "filter": "media_type = 'video'",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["collection_name"] == "test_collection"
    assert body["query"]["query_text"] == "滑雪跃起的动作"
    assert body["query"]["filter"] == "media_type = 'video'"
    assert body["matches"][0]["id"] == "asset_001"
    assert body["usage"]["dashvector_read_units"] == 1


def test_retrieval_embedding_error(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    with patch(
        "app.main.vector_service.retrieve",
        side_effect=query_embedding_failed("DashScope embedding failed", details={"source": "test"}),
    ):
        response = client.post(
            "/v1/assets/retrieval",
            headers={"Authorization": f"Bearer {bundle['access_token']}"},
            json={"query_text": "test"},
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "QUERY_EMBEDDING_FAILED"


def test_retrieval_db_error(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    with patch(
        "app.main.vector_service.retrieve",
        side_effect=retrieval_failed("DashVector query failed", details={"source": "test"}),
    ):
        response = client.post(
            "/v1/assets/retrieval",
            headers={"Authorization": f"Bearer {bundle['access_token']}"},
            json={"query_text": "test"},
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "RETRIEVAL_FAILED"
