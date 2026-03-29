"""向量服务：封装 DashScope 多模态 embedding 与 DashVector 检索。"""
from __future__ import annotations

import base64
import binascii
import logging
from typing import Any

from .config import Settings
from .errors import (
    ServerApiError,
    embedding_provider_unavailable,
    image_decode_failed,
    invalid_retrieval_request,
    invalid_vectorize_request,
    query_embedding_failed,
    retrieval_failed,
    vector_config_error,
    vector_store_unavailable,
    vectorize_write_failed,
)
from .models import (
    AssetRetrievalRequest,
    VectorizeDoc,
    VectorizeRequest,
)

logger = logging.getLogger(__name__)


class VectorService:
    """phase 1 向量化与检索服务。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._embedding_client = None
        self._vector_client = None
        self._collection_cache: dict[str, Any] = {}

    def _ensure_embedding_client(self) -> Any:
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

    def _get_collection(self, collection_name: str) -> Any:
        if collection_name in self._collection_cache:
            return self._collection_cache[collection_name]

        client = self._ensure_vector_client()
        collection = client.get(name=collection_name)
        if collection is None:
            raise vector_store_unavailable(
                "DashVector collection not found.",
                details={"collection_name": collection_name},
            )
        self._collection_cache[collection_name] = collection
        return collection

    def _create_collection(self, collection_name: str, dimension: int) -> Any:
        client = self._ensure_vector_client()
        result = client.create(name=collection_name, dimension=dimension, metric="cosine")
        result_code = getattr(result, "code", getattr(result, "status_code", None))
        if result_code not in {0, "0"}:
            raise vector_store_unavailable(
                "Failed to create DashVector collection.",
                details={
                    "collection_name": collection_name,
                    "status_code": result_code,
                    "message": getattr(result, "message", None),
                },
            )
        self._collection_cache.pop(collection_name, None)
        return self._get_collection(collection_name)

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
        raise embedding_provider_unavailable("Embedding provider returned an invalid embedding payload.")

    def _validate_image_base64(self, image_base64: str, *, doc_id: str) -> str:
        try:
            base64.b64decode(image_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise image_decode_failed(
                "image_base64 is not valid base64.",
                details={"doc_id": doc_id},
            ) from exc
        return f"data:image/jpeg;base64,{image_base64}"

    def _validate_vectorize_request(self, payload: VectorizeRequest) -> None:
        if not payload.docs:
            raise invalid_vectorize_request("docs must contain at least one item.")
        seen_ids: set[str] = set()
        for doc in payload.docs:
            if doc.id in seen_ids:
                raise invalid_vectorize_request(
                    "Duplicate doc.id values are not allowed within one request.",
                    details={"doc_id": doc.id},
                )
            seen_ids.add(doc.id)
            if doc.fields.source_start_ms >= doc.fields.source_end_ms:
                raise invalid_vectorize_request(
                    "source_start_ms must be less than source_end_ms.",
                    details={"doc_id": doc.id},
                )
            self._validate_image_base64(doc.content.image_base64, doc_id=doc.id)

    def _build_image_embedding_input(self, image_base64: str, *, doc_id: str) -> list[dict[str, Any]]:
        return [{"image": self._validate_image_base64(image_base64, doc_id=doc_id)}]

    def _compute_embedding_from_image(self, image_base64: str, *, doc_id: str, model: str, dimension: int) -> list[float]:
        self._ensure_embedding_client()
        try:
            from dashscope import MultiModalEmbedding

            response = MultiModalEmbedding.call(
                api_key=self.settings.dashscope_api_key,
                model=model,
                input=self._build_image_embedding_input(image_base64, doc_id=doc_id),
                dimension=dimension,
            )
            status_code = getattr(response, "status_code", None)
            if status_code not in {200, "200", 0}:
                raise embedding_provider_unavailable(
                    "Embedding provider returned an error.",
                    details={
                        "doc_id": doc_id,
                        "status_code": status_code,
                        "provider_code": getattr(response, "code", None),
                        "request_id": getattr(response, "request_id", None),
                    },
                )
            return self._extract_embedding(getattr(response, "output", None))
        except ServerApiError:
            raise
        except Exception as exc:
            logger.exception("Embedding provider image request failed")
            raise embedding_provider_unavailable(
                f"Embedding provider request failed: {exc}",
                details={"doc_id": doc_id, "error_type": type(exc).__name__},
            ) from exc

    def _compute_query_embedding(self, query_text: str, *, model: str, dimension: int) -> list[float]:
        if not query_text or not query_text.strip():
            raise invalid_retrieval_request("query_text is required and cannot be empty.")
        self._ensure_embedding_client()
        try:
            from dashscope import MultiModalEmbedding

            response = MultiModalEmbedding.call(
                api_key=self.settings.dashscope_api_key,
                model=model,
                input=[{"text": query_text.strip()}],
                dimension=dimension,
            )
            status_code = getattr(response, "status_code", None)
            if status_code not in {200, "200", 0}:
                raise query_embedding_failed(
                    "Embedding provider returned an error while encoding query_text.",
                    details={
                        "status_code": status_code,
                        "provider_code": getattr(response, "code", None),
                        "request_id": getattr(response, "request_id", None),
                    },
                )
            return self._extract_embedding(getattr(response, "output", None))
        except ServerApiError:
            raise
        except Exception as exc:
            logger.exception("Embedding provider query request failed")
            raise query_embedding_failed(
                f"Query embedding request failed: {exc}",
                details={"error_type": type(exc).__name__},
            ) from exc

    def _insert_docs(
        self,
        *,
        collection_name: str,
        partition: str,
        dimension: int,
        vector_docs: list[dict[str, Any]],
    ) -> None:
        try:
            from dashvector import Doc

            try:
                collection = self._get_collection(collection_name)
            except ServerApiError as exc:
                if exc.code != "VECTOR_STORE_UNAVAILABLE":
                    raise
                collection = self._create_collection(collection_name, dimension)
            docs = [
                Doc(
                    id=item["id"],
                    vector=item["vector"],
                    fields=item["fields"],
                )
                for item in vector_docs
            ]
            result = collection.insert(docs, partition=partition)
            result_code = getattr(result, "code", getattr(result, "status_code", None))
            if result_code == -2021:
                collection = self._create_collection(collection_name, dimension)
                result = collection.insert(docs, partition=partition)
                result_code = getattr(result, "code", getattr(result, "status_code", None))
            if result_code not in {0, "0"}:
                raise vectorize_write_failed(
                    "DashVector insert failed.",
                    details={
                        "collection_name": collection_name,
                        "status_code": result_code,
                        "message": getattr(result, "message", None),
                    },
                )
        except ServerApiError:
            raise
        except Exception as exc:
            logger.exception("DashVector insert failed")
            raise vector_store_unavailable(
                f"DashVector insert failed: {exc}",
                details={"collection_name": collection_name, "error_type": type(exc).__name__},
            ) from exc

    def vectorize(self, payload: VectorizeRequest) -> dict[str, Any]:
        self._validate_vectorize_request(payload)

        vector_docs: list[dict[str, Any]] = []
        for doc in payload.docs:
            vector = self._compute_embedding_from_image(
                doc.content.image_base64,
                doc_id=doc.id,
                model=payload.model,
                dimension=payload.dimension,
            )
            vector_docs.append(
                {
                    "id": doc.id,
                    "vector": vector,
                    "fields": doc.fields.model_dump(exclude_none=True),
                }
            )

        self._insert_docs(
            collection_name=payload.collection_name,
            partition=payload.partition,
            dimension=payload.dimension,
            vector_docs=vector_docs,
        )

        return {
            "collection_name": payload.collection_name,
            "partition": payload.partition,
            "model": payload.model,
            "dimension": payload.dimension,
            "inserted_count": len(payload.docs),
            "results": [{"id": doc.id, "status": "inserted"} for doc in payload.docs],
            "usage": {
                "embedding_doc_count": len(payload.docs),
                "dashvector_write_units": len(payload.docs),
            },
        }

    def retrieve(self, payload: AssetRetrievalRequest) -> dict[str, Any]:
        if not payload.query_text or not payload.query_text.strip():
            raise invalid_retrieval_request("query_text is required and cannot be empty.")

        query_vector = self._compute_query_embedding(
            payload.query_text,
            model=payload.model,
            dimension=payload.dimension,
        )
        try:
            collection = self._get_collection(payload.collection_name)
            result = collection.query(
                vector=query_vector,
                topk=payload.topk,
                filter=payload.filter,
                include_vector=payload.include_vector,
                partition=payload.partition,
                output_fields=payload.output_fields,
            )
            result_code = getattr(result, "code", getattr(result, "status_code", None))
            if result_code not in {0, "0"}:
                raise retrieval_failed(
                    "DashVector query failed.",
                    details={
                        "collection_name": payload.collection_name,
                        "status_code": result_code,
                        "message": getattr(result, "message", None),
                    },
                )

            matches = []
            for doc in getattr(result, "output", []) or []:
                match = {
                    "id": doc.id,
                    "score": doc.score,
                    "fields": doc.fields or {},
                }
                if payload.include_vector and hasattr(doc, "vector"):
                    match["vector"] = doc.vector
                matches.append(match)

            return {
                "collection_name": payload.collection_name,
                "partition": payload.partition,
                "query": {
                    "query_text": payload.query_text,
                    "topk": payload.topk,
                    "filter": payload.filter,
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
            raise vector_store_unavailable(
                f"DashVector query failed: {exc}",
                details={"collection_name": payload.collection_name, "error_type": type(exc).__name__},
            ) from exc
