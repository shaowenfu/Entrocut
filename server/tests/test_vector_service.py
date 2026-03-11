"""VectorService 单元测试。"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.errors import vector_config_error, vector_db_error, vector_embedding_error
from app.models import AssetReference
from app.vector_service import VectorService


@pytest.fixture
def mock_settings() -> Settings:
    """创建带有 mock 配置的 Settings。"""
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
    """创建 VectorService 实例。"""
    return VectorService(mock_settings)


class TestVectorServiceConfig:
    """测试配置校验。"""

    def test_raises_config_error_when_dashscope_api_key_missing(self) -> None:
        """DASHSCOPE_API_KEY 未配置时应抛出配置错误。"""
        settings = Settings(dashscope_api_key=None)
        service = VectorService(settings)

        with pytest.raises(Exception) as exc_info:
            service._ensure_embedding_client()

        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "VECTOR_CONFIG_ERROR"

    def test_raises_config_error_when_dashvector_api_key_missing(self) -> None:
        """DASHVECTOR_API_KEY 未配置时应抛出配置错误。"""
        settings = Settings(dashvector_api_key=None, dashvector_endpoint="https://test.com")
        service = VectorService(settings)

        with pytest.raises(Exception) as exc_info:
            service._ensure_vector_client()

        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "VECTOR_CONFIG_ERROR"

    def test_raises_config_error_when_dashvector_endpoint_missing(self) -> None:
        """DASHVECTOR_ENDPOINT 未配置时应抛出配置错误。"""
        settings = Settings(dashvector_api_key="test-key", dashvector_endpoint=None)
        service = VectorService(settings)

        with pytest.raises(Exception) as exc_info:
            service._ensure_vector_client()

        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "VECTOR_CONFIG_ERROR"


class TestBuildMultimodalInput:
    """测试多模态输入构建。"""

    def test_builds_image_url_input(self, vector_service: VectorService) -> None:
        """正确构建 image_url 类型的输入。"""
        refs = [AssetReference(type="image_url", content="https://example.com/image.jpg")]
        result = vector_service._build_multimodal_input(refs)
        assert result == [{"image": "https://example.com/image.jpg"}]

    def test_builds_text_input(self, vector_service: VectorService) -> None:
        """正确构建 text 类型的输入。"""
        refs = [AssetReference(type="text", content="这是测试文本")]
        result = vector_service._build_multimodal_input(refs)
        assert result == [{"text": "这是测试文本"}]

    def test_builds_mixed_inputs(self, vector_service: VectorService) -> None:
        """正确构建融合输入。"""
        refs = [
            AssetReference(type="image_url", content="https://example.com/image.jpg"),
            AssetReference(type="text", content="描述文本"),
        ]
        result = vector_service._build_multimodal_input(refs)
        assert result == [{"image": "https://example.com/image.jpg", "text": "描述文本"}]

    def test_builds_video_input(self, vector_service: VectorService) -> None:
        refs = [AssetReference(type="video_url", content="https://example.com/clip.mp4")]
        result = vector_service._build_multimodal_input(refs)
        assert result == [{"video": "https://example.com/clip.mp4"}]

    def test_duplicate_modalities_raise_error(self, vector_service: VectorService) -> None:
        refs = [
            AssetReference(type="text", content="a"),
            AssetReference(type="text", content="b"),
        ]
        with pytest.raises(Exception) as exc_info:
            vector_service._build_multimodal_input(refs)
        assert exc_info.value.code == "VECTORIZE_ERROR"

    def test_empty_references_returns_empty_list(self, vector_service: VectorService) -> None:
        """空引用列表返回空列表。"""
        result = vector_service._build_multimodal_input([])
        assert result == []


class TestComputeEmbedding:
    """测试 Embedding 计算。"""

    def test_raises_error_for_empty_references(self, vector_service: VectorService) -> None:
        """空引用列表应抛出错误。"""
        with pytest.raises(Exception) as exc_info:
            vector_service.compute_embedding([])
        assert exc_info.value.code == "VECTORIZE_ERROR"

    def test_calls_dashscope_api_correctly(self, vector_service: VectorService) -> None:
        """正确调用 DashScope API。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.output = {"embeddings": [{"embedding": [0.1] * 1024}]}

        mock_multimodal_embedding = MagicMock()
        mock_multimodal_embedding.call.return_value = mock_response

        # 需要在调用前 mock sys.modules 中的 dashscope
        mock_dashscope = MagicMock()
        mock_dashscope.MultiModalEmbedding = mock_multimodal_embedding

        with patch.dict("sys.modules", {"dashscope": mock_dashscope}):
            # 清除缓存的 client，强制重新初始化
            vector_service._embedding_client = None
            vector_service._embedding_client = mock_dashscope
            refs = [AssetReference(type="text", content="测试")]
            result = vector_service.compute_embedding(refs)

        assert result == [0.1] * 1024

    def test_raises_embedding_error_on_api_failure(self, vector_service: VectorService) -> None:
        """API 调用失败时应抛出 embedding 错误。"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.message = "Invalid request"

        mock_multimodal_embedding = MagicMock()
        mock_multimodal_embedding.call.return_value = mock_response

        mock_dashscope = MagicMock()
        mock_dashscope.MultiModalEmbedding = mock_multimodal_embedding

        with patch.dict("sys.modules", {"dashscope": mock_dashscope}):
            vector_service._embedding_client = mock_dashscope
            refs = [AssetReference(type="text", content="测试")]

            with pytest.raises(Exception) as exc_info:
                vector_service.compute_embedding(refs)

            assert exc_info.value.code == "VECTOR_EMBEDDING_ERROR"

    def test_raises_embedding_error_on_invalid_response(self, vector_service: VectorService) -> None:
        """响应格式无效时应抛出 embedding 错误。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.output = {}  # 缺少 embedding

        mock_multimodal_embedding = MagicMock()
        mock_multimodal_embedding.call.return_value = mock_response

        mock_dashscope = MagicMock()
        mock_dashscope.MultiModalEmbedding = mock_multimodal_embedding

        with patch.dict("sys.modules", {"dashscope": mock_dashscope}):
            vector_service._embedding_client = mock_dashscope
            refs = [AssetReference(type="text", content="测试")]

            with pytest.raises(Exception) as exc_info:
                vector_service.compute_embedding(refs)

            assert exc_info.value.code == "VECTOR_EMBEDDING_ERROR"


class TestUpsertVector:
    """测试向量写入。"""

    def test_upserts_vector_successfully(self, vector_service: VectorService) -> None:
        """成功插入向量。"""
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.code = 0
        mock_collection.insert.return_value = mock_result

        mock_doc_class = MagicMock(return_value=MagicMock())

        mock_dashvector = MagicMock()
        mock_dashvector.Doc = mock_doc_class

        with patch.dict("sys.modules", {"dashvector": mock_dashvector}):
            with patch.object(vector_service, "_get_collection", return_value=mock_collection):
                vector_service.upsert_vector(
                    asset_id="test-asset-001",
                    vector=[0.1] * 1024,
                    metadata={"source": "test"},
                )

        mock_collection.insert.assert_called_once()

    def test_raises_db_error_on_upsert_failure(self, vector_service: VectorService) -> None:
        """插入失败时应抛出数据库错误。"""
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.code = 1
        mock_result.message = "Collection not found"
        mock_collection.insert.return_value = mock_result

        mock_doc_class = MagicMock(return_value=MagicMock())
        mock_dashvector = MagicMock()
        mock_dashvector.Doc = mock_doc_class

        with patch.dict("sys.modules", {"dashvector": mock_dashvector}):
            with patch.object(vector_service, "_get_collection", return_value=mock_collection):
                with pytest.raises(Exception) as exc_info:
                    vector_service.upsert_vector(
                        asset_id="test-asset-001",
                        vector=[0.1] * 1024,
                    )

                assert exc_info.value.code == "VECTOR_DB_ERROR"

    def test_creates_collection_and_retries_when_missing(self, vector_service: VectorService) -> None:
        mock_collection = MagicMock()
        first_result = MagicMock()
        first_result.code = -2021
        second_result = MagicMock()
        second_result.code = 0
        mock_collection.insert.side_effect = [first_result, second_result]

        mock_doc_class = MagicMock(return_value=MagicMock())
        mock_dashvector = MagicMock()
        mock_dashvector.Doc = mock_doc_class

        with patch.dict("sys.modules", {"dashvector": mock_dashvector}):
            with patch.object(vector_service, "_get_collection", return_value=mock_collection):
                with patch.object(vector_service, "_create_collection", return_value=mock_collection) as mock_create:
                    vector_service.upsert_vector(
                        asset_id="test-asset-001",
                        vector=[0.1] * 1024,
                    )

        mock_create.assert_called_once()
        assert mock_collection.insert.call_count == 2


class TestVectorize:
    """测试完整的向量化流程。"""

    def test_vectorize_successfully(self, vector_service: VectorService) -> None:
        """成功完成向量化。"""
        mock_embedding = [0.1] * 1024
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.code = 0
        mock_collection.insert.return_value = mock_result

        mock_doc_class = MagicMock(return_value=MagicMock())
        mock_dashvector = MagicMock()
        mock_dashvector.Doc = mock_doc_class

        with patch.dict("sys.modules", {"dashvector": mock_dashvector}):
            with patch.object(vector_service, "compute_embedding", return_value=mock_embedding):
                with patch.object(vector_service, "_get_collection", return_value=mock_collection):
                    refs = [AssetReference(type="text", content="测试")]
                    result = vector_service.vectorize(
                        asset_id="test-asset-001",
                        references=refs,
                        metadata={"source": "test"},
                    )

        assert result.asset_id == "test-asset-001"
        assert result.vector == mock_embedding
        assert result.dimension == 1024

    def test_vectorize_propagates_embedding_error(self, vector_service: VectorService) -> None:
        """Embedding 错误应向上传播。"""
        with patch.object(
            vector_service,
            "compute_embedding",
            side_effect=vector_embedding_error("API failed"),
        ):
            refs = [AssetReference(type="text", content="测试")]

            with pytest.raises(Exception) as exc_info:
                vector_service.vectorize("test-asset", refs)

            assert exc_info.value.code == "VECTOR_EMBEDDING_ERROR"

    def test_vectorize_propagates_db_error(self, vector_service: VectorService) -> None:
        """数据库错误应向上传播。"""
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.status_code = 1
        mock_collection.upsert.return_value = mock_result

        mock_doc_class = MagicMock(return_value=MagicMock())
        mock_dashvector = MagicMock()
        mock_dashvector.Doc = mock_doc_class

        with patch.dict("sys.modules", {"dashvector": mock_dashvector}):
            with patch.object(vector_service, "compute_embedding", return_value=[0.1] * 1024):
                with patch.object(vector_service, "_get_collection", return_value=mock_collection):
                    refs = [AssetReference(type="text", content="测试")]

                    with pytest.raises(Exception) as exc_info:
                        vector_service.vectorize("test-asset", refs)

                    assert exc_info.value.code == "VECTOR_DB_ERROR"
