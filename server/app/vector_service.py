"""向量化服务：封装 DashScope MultiModalEmbedding 和 DashVector SDK。"""
from __future__ import annotations

import logging
from typing import Any

from .config import Settings
from .errors import (
    ServerApiError,
    vector_config_error,
    vector_db_error,
    vector_embedding_error,
    vectorize_error,
)
from .models import AssetReference, AssetVector

logger = logging.getLogger(__name__)


class VectorService:
    """向量化服务，提供「向量化 + 入库」原子操作。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._embedding_client = None
        self._vector_client = None
        self._collection = None

    def _ensure_embedding_client(self) -> Any:
        """懒加载 DashScope Embedding 客户端。"""
        if self._embedding_client is not None:
            return self._embedding_client

        api_key = self.settings.dashscope_api_key
        if not api_key:
            raise vector_config_error("DASHSCOPE_API_KEY is not configured.")

        try:
            import dashscope

            self._embedding_client = dashscope
            return self._embedding_client
        except ImportError as exc:
            raise vector_config_error(
                "dashscope package is not installed.",
                details={"hint": "pip install dashscope"},
            ) from exc

    def _ensure_vector_client(self) -> Any:
        """懒加载 DashVector 客户端。"""
        if self._vector_client is not None:
            return self._vector_client

        api_key = self.settings.dashvector_api_key
        endpoint = self.settings.dashvector_endpoint

        if not api_key or not endpoint:
            raise vector_config_error(
                "DASHVECTOR_API_KEY and DASHVECTOR_ENDPOINT are required.",
                details={
                    "api_key_configured": bool(api_key),
                    "endpoint_configured": bool(endpoint),
                },
            )

        try:
            from dashvector import Client
            try:
                from dashvector import DashVectorProtocol
            except ImportError:
                DashVectorProtocol = None  # type: ignore[assignment]

            protocol: Any = self.settings.dashvector_protocol
            if DashVectorProtocol is not None and isinstance(protocol, str):
                normalized_protocol = protocol.strip().lower()
                if normalized_protocol == "grpc":
                    protocol = DashVectorProtocol.GRPC
                elif normalized_protocol == "http":
                    protocol = DashVectorProtocol.HTTP
            self._vector_client = Client(
                api_key=api_key,
                endpoint=endpoint,
                timeout=self.settings.dashvector_timeout_seconds,
                protocol=protocol,
            )
            return self._vector_client
        except ImportError as exc:
            raise vector_config_error(
                "dashvector package is not installed.",
                details={"hint": "pip install dashvector"},
            ) from exc

    def _get_collection(self, collection_name: str | None = None) -> Any:
        """获取 DashVector Collection。"""
        target_collection = collection_name or self.settings.dashvector_collection_name
        if self._collection is not None and target_collection == self.settings.dashvector_collection_name:
            return self._collection

        client = self._ensure_vector_client()
        collection = client.get(name=target_collection)
        if collection is None:
            raise vector_db_error(
                f"Collection not found: {target_collection}",
                details={"collection_name": target_collection},
            )
        if target_collection == self.settings.dashvector_collection_name:
            self._collection = collection
        return collection

    def _create_collection(self, collection_name: str | None = None) -> Any:
        target_collection = collection_name or self.settings.dashvector_collection_name
        client = self._ensure_vector_client()
        result = client.create(
            name=target_collection,
            dimension=self.settings.dashscope_multimodal_dimension,
            metric="cosine",
        )
        result_code = getattr(result, "code", getattr(result, "status_code", None))
        if result_code not in {0, "0"}:
            raise vector_db_error(
                f"Failed to create collection: {target_collection}",
                details={
                    "collection_name": target_collection,
                    "status_code": result_code,
                    "message": getattr(result, "message", None),
                },
            )
        self._collection = None
        return self._get_collection(target_collection)

    def _build_multimodal_input(self, references: list[AssetReference]) -> list[dict[str, Any]]:
        """将 AssetReference 列表转换为 DashScope MultiModal Embedding 输入格式。"""
        fused_content: dict[str, Any] = {}
        for ref in references:
            if ref.type == "image_url":
                if "image" in fused_content:
                    raise vectorize_error("Multiple image_url references are not supported in one fused embedding request.")
                fused_content["image"] = ref.content
            elif ref.type == "video_url":
                if "video" in fused_content:
                    raise vectorize_error("Multiple video_url references are not supported in one fused embedding request.")
                fused_content["video"] = ref.content
            elif ref.type == "text":
                if "text" in fused_content:
                    raise vectorize_error("Multiple text references are not supported in one fused embedding request.")
                fused_content["text"] = ref.content
        return [fused_content] if fused_content else []

    @staticmethod
    def _extract_embedding(output: Any) -> list[float]:
        if isinstance(output, dict):
            direct_embedding = output.get("embedding")
            if isinstance(direct_embedding, list):
                return direct_embedding
            embeddings = output.get("embeddings")
            if isinstance(embeddings, list) and embeddings:
                first_item = embeddings[0]
                if isinstance(first_item, dict):
                    candidate = first_item.get("embedding") or first_item.get("vector")
                    if isinstance(candidate, list):
                        return candidate
        raise vector_embedding_error(
            "Invalid embedding response from DashScope.",
            details={"response": str(output)[:500]},
        )

    def compute_embedding(self, references: list[AssetReference]) -> list[float]:
        """调用 DashScope MultiModal Embedding API 计算融合向量。"""
        if not references:
            raise vectorize_error("At least one reference is required.")

        self._ensure_embedding_client()
        multimodal_input = self._build_multimodal_input(references)

        if not multimodal_input:
            raise vectorize_error("No valid references to vectorize.")

        try:
            from dashscope import MultiModalEmbedding

            response = MultiModalEmbedding.call(
                api_key=self.settings.dashscope_api_key,
                model=self.settings.dashscope_multimodal_embedding_model,
                input=multimodal_input,
                dimension=self.settings.dashscope_multimodal_dimension,
            )

            status_code = getattr(response, "status_code", None)
            if status_code not in {200, "200", 0}:
                raise vector_embedding_error(
                    f"DashScope embedding API failed: {response.message or 'Unknown error'}",
                    details={
                        "status_code": status_code,
                        "code": getattr(response, "code", None),
                        "request_id": getattr(response, "request_id", None),
                    },
                )
            return self._extract_embedding(getattr(response, "output", None))

        except ServerApiError:
            raise
        except Exception as exc:
            logger.exception("DashScope embedding API call failed")
            raise vector_embedding_error(
                f"DashScope embedding API call failed: {exc}",
                details={"error_type": type(exc).__name__},
            ) from exc

    def upsert_vector(
        self,
        asset_id: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """将向量写入 DashVector。"""
        collection = self._get_collection()

        try:
            from dashvector import Doc

            doc = Doc(
                id=asset_id,
                vector=vector,
                fields=metadata or {},
            )

            result = collection.insert(doc, partition=self.settings.dashvector_partition)
            result_code = getattr(result, "code", getattr(result, "status_code", None))
            if result_code == -2021:
                collection = self._create_collection()
                result = collection.insert(doc, partition=self.settings.dashvector_partition)
                result_code = getattr(result, "code", getattr(result, "status_code", None))
            if result_code not in {0, "0"}:
                raise vector_db_error(
                    f"Failed to insert vector for asset: {asset_id}",
                    details={
                        "status_code": result_code,
                        "message": getattr(result, "message", None),
                    },
                )

        except ServerApiError:
            raise
        except Exception as exc:
            logger.exception("DashVector upsert failed")
            raise vector_db_error(
                f"DashVector insert failed: {exc}",
                details={"asset_id": asset_id, "error_type": type(exc).__name__},
            ) from exc

    def vectorize(
        self,
        asset_id: str,
        references: list[AssetReference],
        metadata: dict[str, Any] | None = None,
    ) -> AssetVector:
        """原子操作：计算向量 + 写入数据库。"""
        # Step 1: 计算 embedding
        vector = self.compute_embedding(references)

        # Step 2: 写入向量数据库
        self.upsert_vector(asset_id, vector, metadata)

        return AssetVector(
            asset_id=asset_id,
            vector=vector,
            dimension=len(vector),
        )

    def compute_query_embedding(self, query_text: str) -> list[float]:
        """将查询文本转换为融合向量。"""
        if not query_text or not query_text.strip():
            raise vectorize_error("query_text cannot be empty.")

        self._ensure_embedding_client()

        try:
            from dashscope import MultiModalEmbedding

            response = MultiModalEmbedding.call(
                api_key=self.settings.dashscope_api_key,
                model=self.settings.dashscope_multimodal_embedding_model,
                input=[{"text": query_text.strip()}],
                dimension=self.settings.dashscope_multimodal_dimension,
            )

            status_code = getattr(response, "status_code", None)
            if status_code not in {200, "200", 0}:
                raise vector_embedding_error(
                    f"DashScope embedding API failed: {response.message or 'Unknown error'}",
                    details={
                        "status_code": status_code,
                        "code": getattr(response, "code", None),
                        "request_id": getattr(response, "request_id", None),
                    },
                )
            return self._extract_embedding(getattr(response, "output", None))

        except ServerApiError:
            raise
        except Exception as exc:
            logger.exception("DashScope query embedding API call failed")
            raise vector_embedding_error(
                f"DashScope query embedding API call failed: {exc}",
                details={"error_type": type(exc).__name__},
            ) from exc

    def retrieve(
        self,
        collection_name: str | None = None,
        partition: str | None = None,
        model: str | None = None,
        dimension: int | None = None,
        query_text: str | None = None,
        topk: int = 8,
        filter_str: str | None = None,
        include_vector: bool = False,
        output_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """执行语义检索：生成查询向量 + 向量检索。"""
        # 参数校验
        if not query_text or not query_text.strip():
            raise vectorize_error("query_text is required and cannot be empty.")

        # Step 1: 生成查询向量
        query_vector = self.compute_query_embedding(query_text)

        # Step 2: 获取 Collection
        collection = self._get_collection(collection_name)

        # Step 3: 执行检索
        try:
            result = collection.query(
                vector=query_vector,
                topk=topk,
                filter=filter_str,
                include_vector=include_vector,
                partition=partition or self.settings.dashvector_partition,
                output_fields=output_fields,
            )

            result_code = getattr(result, "code", getattr(result, "status_code", None))
            if result_code not in {0, "0"}:
                # Collection 不存在的特殊处理
                if result_code == 1004:  # DashVector collection not found error code
                    raise vector_db_error(
                        f"Collection not found: {collection_name or self.settings.dashvector_collection_name}",
                        details={
                            "status_code": result_code,
                            "message": getattr(result, "message", None),
                        },
                    )
                raise vector_db_error(
                    f"DashVector query failed: {getattr(result, 'message', None) or 'Unknown error'}",
                    details={
                        "status_code": result_code,
                        "message": getattr(result, "message", None),
                    },
                )

            # Step 4: 组装响应
            matches = []
            for doc in result.output:
                match = {
                    "id": doc.id,
                    "score": doc.score,
                    "fields": doc.fields or {},
                }
                if include_vector and hasattr(doc, "vector"):
                    match["vector"] = doc.vector
                matches.append(match)

            return {
                "collection_name": collection_name or self.settings.dashvector_collection_name,
                "partition": partition or self.settings.dashvector_partition,
                "query": {
                    "query_text": query_text,
                    "topk": topk,
                    "filter": filter_str,
                },
                "matches": matches,
                "usage": {
                    "embedding_query_count": 1,
                    "dashvector_read_units": len(matches),
                },
            }

        except ServerApiError:
            raise
        except Exception as exc:
            logger.exception("DashVector query failed")
            raise vector_db_error(
                f"DashVector query failed: {exc}",
                details={"error_type": type(exc).__name__},
            ) from exc
