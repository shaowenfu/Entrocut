"""/v1/assets/vectorize 路由集成测试。"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth_service import new_id
from app.auth_store import now_utc, to_iso
from app.main import app, settings, store, token_service
from app.models import AssetVector


@pytest.fixture
def client() -> TestClient:
    """创建 TestClient。"""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _configure_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(settings, "allow_inmemory_mongo_fallback", True)
    monkeypatch.setattr(settings, "allow_inmemory_redis_fallback", True)


@pytest.fixture
def test_user() -> dict[str, Any]:
    """创建测试用户。"""
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
    """创建认证头。"""
    bundle = token_service.issue_session_bundle(test_user)
    return {
        "Authorization": f"Bearer {bundle['access_token']}",
        "Content-Type": "application/json",
    }


class TestVectorizeAuth:
    """测试认证相关。"""

    def test_requires_bearer_token(self, client: TestClient) -> None:
        """未提供 Bearer token 应返回 401。"""
        response = client.post(
            "/v1/assets/vectorize",
            json={
                "asset_id": "test-asset",
                "references": [{"type": "text", "content": "test"}],
            },
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"

    def test_invalid_token_returns_401(self, client: TestClient) -> None:
        """无效 token 应返回 401。"""
        response = client.post(
            "/v1/assets/vectorize",
            headers={"Authorization": "Bearer invalid-token"},
            json={
                "asset_id": "test-asset",
                "references": [{"type": "text", "content": "test"}],
            },
        )
        assert response.status_code == 401


class TestVectorizeValidation:
    """测试请求验证。"""

    def test_requires_asset_id(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """缺少 asset_id 应返回 422。"""
        response = client.post(
            "/v1/assets/vectorize",
            headers=auth_headers,
            json={
                "references": [{"type": "text", "content": "test"}],
            },
        )
        assert response.status_code == 422

    def test_requires_references(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """缺少 references 应返回 422。"""
        response = client.post(
            "/v1/assets/vectorize",
            headers=auth_headers,
            json={
                "asset_id": "test-asset",
            },
        )
        assert response.status_code == 422

    def test_references_must_not_be_empty(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """空 references 应返回 422。"""
        response = client.post(
            "/v1/assets/vectorize",
            headers=auth_headers,
            json={
                "asset_id": "test-asset",
                "references": [],
            },
        )
        assert response.status_code == 422

    def test_reference_requires_type(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """reference 缺少 type 应返回 422。"""
        response = client.post(
            "/v1/assets/vectorize",
            headers=auth_headers,
            json={
                "asset_id": "test-asset",
                "references": [{"content": "test"}],
            },
        )
        assert response.status_code == 422

    def test_reference_requires_content(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """reference 缺少 content 应返回 422。"""
        response = client.post(
            "/v1/assets/vectorize",
            headers=auth_headers,
            json={
                "asset_id": "test-asset",
                "references": [{"type": "text"}],
            },
        )
        assert response.status_code == 422


class TestVectorizeSuccess:
    """测试成功场景。"""

    def test_vectorize_text_successfully(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """成功向量化文本。"""
        mock_result = AssetVector(
            asset_id="test-asset-001",
            vector=[0.1] * 1024,
            dimension=1024,
        )

        with patch("app.main.vector_service.vectorize", return_value=mock_result):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json={
                    "asset_id": "test-asset-001",
                    "references": [
                        {"type": "text", "content": "这是一段测试文本"}
                    ],
                    "metadata": {"source": "unit_test"},
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert len(body["vectors"]) == 1
        assert body["vectors"][0]["asset_id"] == "test-asset-001"
        assert body["vectors"][0]["dimension"] == 1024

    def test_vectorize_image_url_successfully(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """成功向量化图片 URL。"""
        mock_result = AssetVector(
            asset_id="test-asset-002",
            vector=[0.2] * 1024,
            dimension=1024,
        )

        with patch("app.main.vector_service.vectorize", return_value=mock_result):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json={
                    "asset_id": "test-asset-002",
                    "references": [
                        {
                            "type": "image_url",
                            "content": "https://example.com/image.jpg",
                        }
                    ],
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["vectors"][0]["asset_id"] == "test-asset-002"

    def test_vectorize_multimodal_successfully(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """成功向量化多模态内容（图片 + 文本）。"""
        mock_result = AssetVector(
            asset_id="test-asset-003",
            vector=[0.3] * 1024,
            dimension=1024,
        )

        with patch("app.main.vector_service.vectorize", return_value=mock_result):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json={
                    "asset_id": "test-asset-003",
                    "references": [
                        {
                            "type": "image_url",
                            "content": "https://example.com/photo.jpg",
                        },
                        {"type": "text", "content": "这张照片拍摄于2024年"},
                    ],
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"


class TestVectorizeErrors:
    """测试错误场景。"""

    def test_returns_error_envelope_on_config_error(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """配置错误应返回 ErrorEnvelope 格式。"""
        from app.errors import vector_config_error

        with patch(
            "app.main.vector_service.vectorize",
            side_effect=vector_config_error("DASHSCOPE_API_KEY not configured"),
        ):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json={
                    "asset_id": "test-asset",
                    "references": [{"type": "text", "content": "test"}],
                },
            )

        assert response.status_code == 503
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "VECTOR_CONFIG_ERROR"
        assert body["error"]["type"] == "server_error"

    def test_returns_error_envelope_on_embedding_error(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Embedding 错误应返回 ErrorEnvelope 格式。"""
        from app.errors import vector_embedding_error

        with patch(
            "app.main.vector_service.vectorize",
            side_effect=vector_embedding_error("DashScope API failed"),
        ):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json={
                    "asset_id": "test-asset",
                    "references": [{"type": "text", "content": "test"}],
                },
            )

        assert response.status_code == 502
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "VECTOR_EMBEDDING_ERROR"

    def test_returns_error_envelope_on_db_error(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """数据库错误应返回 ErrorEnvelope 格式。"""
        from app.errors import vector_db_error

        with patch(
            "app.main.vector_service.vectorize",
            side_effect=vector_db_error("DashVector upsert failed"),
        ):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json={
                    "asset_id": "test-asset",
                    "references": [{"type": "text", "content": "test"}],
                },
            )

        assert response.status_code == 502
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "VECTOR_DB_ERROR"


class TestVectorizeResponseFormat:
    """测试响应格式。"""

    def test_response_includes_request_id(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """响应应包含 X-Request-ID。"""
        mock_result = AssetVector(
            asset_id="test-asset",
            vector=[0.1] * 1024,
            dimension=1024,
        )

        with patch("app.main.vector_service.vectorize", return_value=mock_result):
            response = client.post(
                "/v1/assets/vectorize",
                headers={**auth_headers, "X-Request-ID": "req_test_001"},
                json={
                    "asset_id": "test-asset",
                    "references": [{"type": "text", "content": "test"}],
                },
            )

        assert response.headers.get("X-Request-ID") == "req_test_001"

    def test_response_matches_vectorize_response_model(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """响应应符合 VectorizeResponse 模型。"""
        mock_result = AssetVector(
            asset_id="test-asset",
            vector=[0.1] * 1024,
            dimension=1024,
        )

        with patch("app.main.vector_service.vectorize", return_value=mock_result):
            response = client.post(
                "/v1/assets/vectorize",
                headers=auth_headers,
                json={
                    "asset_id": "test-asset",
                    "references": [{"type": "text", "content": "test"}],
                },
            )

        body = response.json()
        assert "status" in body
        assert "vectors" in body
        assert body["status"] in ["success", "partial_success", "failed"]
        assert isinstance(body["vectors"], list)
