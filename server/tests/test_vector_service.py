"""VectorService 单元测试。"""
from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.errors import (
    embedding_provider_unavailable,
    image_decode_failed,
    invalid_retrieval_request,
    invalid_vectorize_request,
    query_embedding_failed,
    retrieval_failed,
    vector_store_unavailable,
    vectorize_write_failed,
)
from app.models import AssetRetrievalRequest, VectorizeRequest
from app.vector_service import VectorService


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        dashscope_api_key="test-dashscope-key",
        dashscope_multimodal_embedding_model="qwen3-vl-embedding",
        dashscope_multimodal_dimension=1024,
        dashvector_api_key="test-dashvector-key",
        dashvector_endpoint="https://test-endpoint.dashvector.cn",
        dashvector_collection_name="test_collection",
        dashvector_partition="default",
        dashvector_timeout_seconds=10,
        dashvector_protocol="grpc",
    )


@pytest.fixture
def vector_service(mock_settings: Settings) -> VectorService:
    return VectorService(mock_settings)


def _make_vectorize_request() -> VectorizeRequest:
    return VectorizeRequest.model_validate(
        {
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
    )


def _make_retrieval_request() -> AssetRetrievalRequest:
    return AssetRetrievalRequest.model_validate(
        {
            "collection_name": "entrocut_assets",
            "partition": "default",
            "model": "qwen3-vl-embedding",
            "dimension": 1024,
            "query_text": "旅行视频开头，明显带出发感的镜头",
            "topk": 8,
            "filter": "project_id = 'proj_001'",
        }
    )


class TestVectorServiceConfig:
    def test_raises_config_error_when_dashscope_api_key_missing(self) -> None:
        service = VectorService(Settings(dashscope_api_key=None))
        with pytest.raises(Exception) as exc_info:
            service._ensure_embedding_client()
        assert exc_info.value.code == "VECTOR_CONFIG_ERROR"

    def test_raises_config_error_when_dashvector_api_key_missing(self) -> None:
        service = VectorService(Settings(dashvector_api_key=None, dashvector_endpoint="https://test.com"))
        with pytest.raises(Exception) as exc_info:
            service._ensure_vector_client()
        assert exc_info.value.code == "VECTOR_CONFIG_ERROR"


class TestVectorizeValidation:
    def test_rejects_duplicate_doc_ids(self, vector_service: VectorService) -> None:
        payload = VectorizeRequest.model_validate(
            {
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
                        },
                    },
                    {
                        "id": "clip_001",
                        "content": {"image_base64": "QkJCQkJCQkJCQkJCQkJCQg=="},
                        "fields": {
                            "clip_id": "clip_002",
                            "asset_id": "asset_001",
                            "project_id": "proj_001",
                            "source_start_ms": 5000,
                            "source_end_ms": 6200,
                        },
                    },
                ]
            }
        )
        with pytest.raises(Exception) as exc_info:
            vector_service._validate_vectorize_request(payload)
        assert exc_info.value.code == "INVALID_VECTORIZE_REQUEST"

    def test_rejects_invalid_image_base64(self, vector_service: VectorService) -> None:
        with pytest.raises(Exception) as exc_info:
            vector_service._validate_image_base64("not-base64", doc_id="clip_001")
        assert exc_info.value.code == "IMAGE_DECODE_FAILED"


class TestComputeEmbedding:
    def test_compute_image_embedding_successfully(self, vector_service: VectorService) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.output = {"embeddings": [{"embedding": [0.1] * 1024}]}
        mock_multimodal_embedding = MagicMock()
        mock_multimodal_embedding.call.return_value = mock_response
        mock_dashscope = MagicMock()
        mock_dashscope.MultiModalEmbedding = mock_multimodal_embedding

        with patch.dict("sys.modules", {"dashscope": mock_dashscope}):
            vector_service._embedding_client = mock_dashscope
            result = vector_service._compute_embedding_from_image(
                "QUFBQUFBQUFBQUFBQUFBQQ==",
                doc_id="clip_001",
                model="qwen3-vl-embedding",
                dimension=1024,
            )

        assert result == [0.1] * 1024

    def test_compute_query_embedding_raises_provider_error(self, vector_service: VectorService) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.code = "InternalError"
        mock_multimodal_embedding = MagicMock()
        mock_multimodal_embedding.call.return_value = mock_response
        mock_dashscope = MagicMock()
        mock_dashscope.MultiModalEmbedding = mock_multimodal_embedding

        with patch.dict("sys.modules", {"dashscope": mock_dashscope}):
            vector_service._embedding_client = mock_dashscope
            with pytest.raises(Exception) as exc_info:
                vector_service._compute_query_embedding(
                    "test query",
                    model="qwen3-vl-embedding",
                    dimension=1024,
                )

        assert exc_info.value.code == "QUERY_EMBEDDING_FAILED"


class TestInsertDocs:
    def test_insert_docs_successfully(self, vector_service: VectorService) -> None:
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.code = 0
        mock_collection.insert.return_value = mock_result
        mock_doc_class = MagicMock(return_value=MagicMock())
        mock_dashvector = MagicMock()
        mock_dashvector.Doc = mock_doc_class

        with patch.dict("sys.modules", {"dashvector": mock_dashvector}):
            with patch.object(vector_service, "_get_collection", return_value=mock_collection):
                vector_service._insert_docs(
                    collection_name="entrocut_assets",
                    partition="default",
                    dimension=1024,
                    vector_docs=[
                        {"id": "clip_001", "vector": [0.1] * 1024, "fields": {"clip_id": "clip_001"}}
                    ],
                )

        mock_collection.insert.assert_called_once()

    def test_insert_docs_raises_write_failed(self, vector_service: VectorService) -> None:
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.code = 1
        mock_result.message = "failed"
        mock_collection.insert.return_value = mock_result
        mock_doc_class = MagicMock(return_value=MagicMock())
        mock_dashvector = MagicMock()
        mock_dashvector.Doc = mock_doc_class

        with patch.dict("sys.modules", {"dashvector": mock_dashvector}):
            with patch.object(vector_service, "_get_collection", return_value=mock_collection):
                with pytest.raises(Exception) as exc_info:
                    vector_service._insert_docs(
                        collection_name="entrocut_assets",
                        partition="default",
                        dimension=1024,
                        vector_docs=[
                            {"id": "clip_001", "vector": [0.1] * 1024, "fields": {"clip_id": "clip_001"}}
                        ],
                    )
        assert exc_info.value.code == "VECTORIZE_WRITE_FAILED"


class TestVectorize:
    def test_vectorize_successfully(self, vector_service: VectorService) -> None:
        payload = _make_vectorize_request()
        with patch.object(vector_service, "_compute_embedding_from_image", return_value=[0.1] * 1024):
            with patch.object(vector_service, "_insert_docs", return_value=None):
                result = vector_service.vectorize(payload)
        assert result["inserted_count"] == 1
        assert result["results"][0]["id"] == "clip_001"

    def test_vectorize_propagates_embedding_error(self, vector_service: VectorService) -> None:
        payload = _make_vectorize_request()
        with patch.object(
            vector_service,
            "_compute_embedding_from_image",
            side_effect=embedding_provider_unavailable("provider failed"),
        ):
            with pytest.raises(Exception) as exc_info:
                vector_service.vectorize(payload)
        assert exc_info.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"


class TestRetrieve:
    def test_retrieve_successfully(self, vector_service: VectorService) -> None:
        payload = _make_retrieval_request()
        mock_collection = MagicMock()
        mock_doc = MagicMock()
        mock_doc.id = "clip_001"
        mock_doc.score = 0.91
        mock_doc.fields = {"clip_id": "clip_001", "asset_id": "asset_001"}
        mock_result = MagicMock()
        mock_result.code = 0
        mock_result.output = [mock_doc]
        mock_collection.query.return_value = mock_result

        with patch.object(vector_service, "_compute_query_embedding", return_value=[0.1] * 1024):
            with patch.object(vector_service, "_get_collection", return_value=mock_collection):
                result = vector_service.retrieve(payload)

        assert result["matches"][0]["id"] == "clip_001"
        assert result["usage"]["embedding_query_count"] == 1

    def test_retrieve_rejects_empty_query(self, vector_service: VectorService) -> None:
        payload = AssetRetrievalRequest.model_validate({"query_text": "x"})
        payload.query_text = ""
        with pytest.raises(Exception) as exc_info:
            vector_service.retrieve(payload)
        assert exc_info.value.code == "INVALID_RETRIEVAL_REQUEST"

    def test_retrieve_propagates_query_embedding_failed(self, vector_service: VectorService) -> None:
        payload = _make_retrieval_request()
        with patch.object(
            vector_service,
            "_compute_query_embedding",
            side_effect=query_embedding_failed("query failed"),
        ):
            with pytest.raises(Exception) as exc_info:
                vector_service.retrieve(payload)
        assert exc_info.value.code == "QUERY_EMBEDDING_FAILED"

    def test_retrieve_raises_retrieval_failed_on_query_error(self, vector_service: VectorService) -> None:
        payload = _make_retrieval_request()
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.code = 1
        mock_result.message = "bad query"
        mock_collection.query.return_value = mock_result

        with patch.object(vector_service, "_compute_query_embedding", return_value=[0.1] * 1024):
            with patch.object(vector_service, "_get_collection", return_value=mock_collection):
                with pytest.raises(Exception) as exc_info:
                    vector_service.retrieve(payload)

        assert exc_info.value.code == "RETRIEVAL_FAILED"
