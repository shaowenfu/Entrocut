"""/v1/assets/vectorize 路由集成测试。"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth_service import new_id
from app.auth_store import now_utc, to_iso
from app.main import app, settings, store, token_service


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _configure_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(settings, "allow_inmemory_mongo_fallback", True)
    monkeypatch.setattr(settings, "allow_inmemory_redis_fallback", True)


@pytest.fixture
def test_user() -> dict[str, Any]:
    current_time = now_utc()
    user = {
        "_id": new_id("user"),
        "email": f"{new_id('mail')}@vector.local",
        "display_name": "Vector Test User",
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


@pytest.fixture
def auth_headers(test_user: dict[str, Any]) -> dict[str, str]:
    bundle = token_service.issue_session_bundle(test_user)
    return {
        "Authorization": f"Bearer {bundle['access_token']}",
        "Content-Type": "application/json",
    }


def _make_vectorize_payload() -> dict[str, Any]:
    return {
        "collection_name": "entrocut_assets",
        "partition": "default",
        "model": "qwen3-vl-embedding",
        "dimension": 1024,
        "docs": [
            {
                "id": "clip_001",
                "content": {"image_base64": "QUFBQUFBQUFBQUFBQUFBQQ=="},
                "fields": {
                    "clip_id": "clip_001",
                    "asset_id": "asset_001",
                    "project_id": "proj_001",
                    "source_start_ms": 1000,
                    "source_end_ms": 4200,
                    "frame_count": 4,
                },
            }
        ],
    }


class TestVectorizeAuth:
    def test_requires_bearer_token(self, client: TestClient) -> None:
        response = client.post("/v1/assets/vectorize", json=_make_vectorize_payload())
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"

    def test_invalid_token_returns_401(self, client: TestClient) -> None:
        response = client.post(
            "/v1/assets/vectorize",
            headers={"Authorization": "Bearer invalid-token"},
            json=_make_vectorize_payload(),
        )
        assert response.status_code == 401


class TestVectorizeValidation:
    def test_requires_docs(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        response = client.post(
            "/v1/assets/vectorize",
            headers=auth_headers,
            json={"collection_name": "entrocut_assets", "docs": []},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_VECTORIZE_REQUEST"

    def test_requires_image_base64(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        payload = _make_vectorize_payload()
        del payload["docs"][0]["content"]["image_base64"]
        response = client.post("/v1/assets/vectorize", headers=auth_headers, json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_VECTORIZE_REQUEST"

    def test_requires_fields(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        payload = _make_vectorize_payload()
        del payload["docs"][0]["fields"]
        response = client.post("/v1/assets/vectorize", headers=auth_headers, json=payload)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_VECTORIZE_REQUEST"


class TestVectorizeSuccess:
    def test_vectorize_successfully(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        mock_result = {
            "collection_name": "entrocut_assets",
            "partition": "default",
            "model": "qwen3-vl-embedding",
            "dimension": 1024,
            "inserted_count": 1,
            "results": [{"id": "clip_001", "status": "inserted"}],
            "usage": {"embedding_doc_count": 1, "dashvector_write_units": 1},
        }

        with patch("app.main.vector_service.vectorize", return_value=mock_result):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json=_make_vectorize_payload(),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["collection_name"] == "entrocut_assets"
        assert body["inserted_count"] == 1
        assert body["results"][0]["id"] == "clip_001"
        assert body["results"][0]["status"] == "inserted"


class TestVectorizeErrors:
    def test_returns_error_on_invalid_request_error(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        from app.errors import invalid_vectorize_request

        with patch(
            "app.main.vector_service.vectorize",
            side_effect=invalid_vectorize_request("Duplicate doc id."),
        ):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json=_make_vectorize_payload(),
            )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_VECTORIZE_REQUEST"

    def test_returns_error_on_embedding_failure(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        from app.errors import embedding_provider_unavailable

        with patch(
            "app.main.vector_service.vectorize",
            side_effect=embedding_provider_unavailable("DashScope failed"),
        ):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json=_make_vectorize_payload(),
            )

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "EMBEDDING_PROVIDER_UNAVAILABLE"

    def test_returns_error_on_vector_store_failure(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        from app.errors import vector_store_unavailable

        with patch(
            "app.main.vector_service.vectorize",
            side_effect=vector_store_unavailable("DashVector failed"),
        ):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json=_make_vectorize_payload(),
            )

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "VECTOR_STORE_UNAVAILABLE"


class TestVectorizeResponseFormat:
    def test_response_includes_request_id(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        mock_result = {
            "collection_name": "entrocut_assets",
            "partition": "default",
            "model": "qwen3-vl-embedding",
            "dimension": 1024,
            "inserted_count": 1,
            "results": [{"id": "clip_001", "status": "inserted"}],
            "usage": {"embedding_doc_count": 1, "dashvector_write_units": 1},
        }
        with patch("app.main.vector_service.vectorize", return_value=mock_result):
            response = client.post(
                "/v1/assets/vectorize",
                headers={**auth_headers, "X-Request-ID": "req_test_001"},
                json=_make_vectorize_payload(),
            )
        assert response.headers.get("X-Request-ID") == "req_test_001"

    def test_response_matches_new_vectorize_response_model(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        mock_result = {
            "collection_name": "entrocut_assets",
            "partition": "default",
            "model": "qwen3-vl-embedding",
            "dimension": 1024,
            "inserted_count": 1,
            "results": [{"id": "clip_001", "status": "inserted"}],
            "usage": {"embedding_doc_count": 1, "dashvector_write_units": 1},
        }
        with patch("app.main.vector_service.vectorize", return_value=mock_result):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json=_make_vectorize_payload(),
            )
        body = response.json()
        assert "collection_name" in body
        assert "partition" in body
        assert "model" in body
        assert "dimension" in body
        assert "inserted_count" in body
        assert "results" in body
