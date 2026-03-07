from __future__ import annotations

import base64
import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from dashscope import MultiModalEmbedding
from dashscope.embeddings.multimodal_embedding import MultiModalEmbeddingItemImage, MultiModalEmbeddingItemText
from dashvector import Client, Collection, Doc
from dashvector.common.error import DashVectorException
from dashvector.common.types import DashVectorCode

from app.adapters.contracts import EmbeddingAdapter, ProxyResult, VectorSearchAdapter

_FILTERABLE_STRING_FIELDS = {"user_id", "project_id", "asset_id", "clip_id"}
_FILTERABLE_NUMERIC_FIELDS = {"start_ms", "end_ms", "score"}


def _error_payload(
    *,
    error_code: str,
    provider: str,
    message: str,
    retryable: bool,
    provider_code: str | int | None = None,
    provider_request_id: str | None = None,
    provider_status: str | None = None,
) -> dict[str, Any]:
    return {
        "error_code": error_code,
        "message": message,
        "retryable": retryable,
        "provider": provider,
        "provider_code": provider_code,
        "provider_request_id": provider_request_id,
        "provider_status": provider_status,
    }


def _is_data_uri(value: str) -> bool:
    return value.startswith("data:image/")


def _looks_like_base64(value: str) -> bool:
    stripped = "".join(value.split())
    if not stripped or len(stripped) % 4 != 0:
        return False
    return re.fullmatch(r"[A-Za-z0-9+/=]+", stripped) is not None


def _normalize_image_input(image_b64: str) -> str:
    raw_value = image_b64.strip()
    if not raw_value:
        raise ValueError("image payload is empty")
    if _is_data_uri(raw_value):
        return raw_value
    if _looks_like_base64(raw_value):
        try:
            base64.b64decode(raw_value, validate=True)
        except Exception as exc:  # pragma: no cover - defensive branch
            raise ValueError("image payload is not valid base64") from exc
        return f"data:image/jpeg;base64,{raw_value}"
    raise ValueError("image payload must be base64 or data URI")


def _normalize_text_input(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        raise ValueError("text payload is empty")
    return normalized


def _escape_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _sanitize_partition_name(user_id: str) -> str:
    digest = hashlib.sha1(user_id.encode("utf-8")).hexdigest()[:12]
    readable = re.sub(r"[^A-Za-z0-9_-]+", "_", user_id).strip("_")[:10] or "user"
    return f"u_{readable}_{digest}"


def _build_dashvector_filter(filters: dict[str, Any]) -> str | None:
    clauses: list[str] = []
    for key in sorted(filters):
        value = filters[key]
        if value in (None, ""):
            continue
        if key in _FILTERABLE_STRING_FIELDS:
            clauses.append(f"{key} = '{_escape_filter_value(str(value))}'")
            continue
        if key in _FILTERABLE_NUMERIC_FIELDS and isinstance(value, (int, float)):
            clauses.append(f"{key} = {value}")
            continue
        if isinstance(value, dict):
            gte = value.get("gte")
            lte = value.get("lte")
            if key in _FILTERABLE_NUMERIC_FIELDS and isinstance(gte, (int, float)):
                clauses.append(f"{key} >= {gte}")
            if key in _FILTERABLE_NUMERIC_FIELDS and isinstance(lte, (int, float)):
                clauses.append(f"{key} <= {lte}")
    return " and ".join(clauses) or None


def _extract_embedding_vector(output: Any) -> list[float]:
    if isinstance(output, dict):
        embeddings = output.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            item = embeddings[0]
            if isinstance(item, dict) and isinstance(item.get("embedding"), list):
                return [float(value) for value in item["embedding"]]
        embedding = output.get("embedding")
        if isinstance(embedding, list):
            return [float(value) for value in embedding]
    raise ValueError("embedding vector missing in provider response")


def _map_dashscope_failure(response: Any) -> ProxyResult:
    provider_code = getattr(response, "code", None)
    message = str(getattr(response, "message", "") or "DashScope request failed.")
    status_code = int(getattr(response, "status_code", 0) or 0)
    request_id = getattr(response, "request_id", None)
    lowered = f"{provider_code or ''} {message}".lower()
    if status_code == 429 or "throttl" in lowered or "rate" in lowered:
        return ProxyResult(
            ok=False,
            payload=_error_payload(
                error_code="SERVER_PROVIDER_RATE_LIMITED",
                provider="dashscope",
                message=message,
                retryable=True,
                provider_code=provider_code or status_code,
                provider_request_id=request_id,
                provider_status="rate_limited",
            ),
        )
    if "quota" in lowered or "bill" in lowered:
        return ProxyResult(
            ok=False,
            payload=_error_payload(
                error_code="SERVER_PROVIDER_QUOTA_EXCEEDED",
                provider="dashscope",
                message=message,
                retryable=False,
                provider_code=provider_code or status_code,
                provider_request_id=request_id,
                provider_status="quota_exceeded",
            ),
        )
    return ProxyResult(
        ok=False,
        payload=_error_payload(
            error_code="SERVER_PROVIDER_UNAVAILABLE",
            provider="dashscope",
            message=message,
            retryable=status_code >= 500 or status_code == 0,
            provider_code=provider_code or status_code,
            provider_request_id=request_id,
            provider_status="provider_error",
        ),
    )


def _map_dashscope_exception(exc: Exception) -> ProxyResult:
    lowered = str(exc).lower()
    if "quota" in lowered:
        return ProxyResult(
            ok=False,
            payload=_error_payload(
                error_code="SERVER_PROVIDER_QUOTA_EXCEEDED",
                provider="dashscope",
                message=str(exc),
                retryable=False,
                provider_status="quota_exceeded",
            ),
        )
    if "throttl" in lowered or "rate" in lowered:
        return ProxyResult(
            ok=False,
            payload=_error_payload(
                error_code="SERVER_PROVIDER_RATE_LIMITED",
                provider="dashscope",
                message=str(exc),
                retryable=True,
                provider_status="rate_limited",
            ),
        )
    return ProxyResult(
        ok=False,
        payload=_error_payload(
            error_code="SERVER_PROVIDER_UNAVAILABLE",
            provider="dashscope",
            message=str(exc),
            retryable=True,
            provider_status="provider_exception",
        ),
    )


def _map_dashvector_response(response: Any, *, success_payload: dict[str, Any]) -> ProxyResult:
    if getattr(response, "code", None) == DashVectorCode.Success:
        payload = dict(success_payload)
        payload["provider"] = "dashvector"
        payload["provider_request_id"] = getattr(response, "request_id", None)
        payload["provider_status"] = "ok"
        payload["usage"] = getattr(response, "usage", None)
        return ProxyResult(ok=True, payload=payload)

    message = str(getattr(response, "message", "") or "DashVector request failed.")
    code = getattr(response, "code", None)
    lowered = f"{code or ''} {message}".lower()
    if "quota" in lowered:
        return ProxyResult(
            ok=False,
            payload=_error_payload(
                error_code="SERVER_PROVIDER_QUOTA_EXCEEDED",
                provider="dashvector",
                message=message,
                retryable=False,
                provider_code=code,
                provider_request_id=getattr(response, "request_id", None),
                provider_status="quota_exceeded",
            ),
        )
    if "throttl" in lowered or "rate" in lowered:
        return ProxyResult(
            ok=False,
            payload=_error_payload(
                error_code="SERVER_PROVIDER_RATE_LIMITED",
                provider="dashvector",
                message=message,
                retryable=True,
                provider_code=code,
                provider_request_id=getattr(response, "request_id", None),
                provider_status="rate_limited",
            ),
        )
    return ProxyResult(
        ok=False,
        payload=_error_payload(
            error_code="SERVER_PROVIDER_UNAVAILABLE",
            provider="dashvector",
            message=message,
            retryable=True,
            provider_code=code,
            provider_request_id=getattr(response, "request_id", None),
            provider_status="provider_error",
        ),
    )


@dataclass(slots=True)
class AliyunEmbeddingAdapter(EmbeddingAdapter):
    api_key: str
    model: str = "qwen3-vl-embedding"
    workspace: str | None = None
    timeout_seconds: float = 30.0

    def embed(self, content: str, *, modality: str = "image") -> ProxyResult:
        try:
            item = self._build_item(content, modality=modality)
            response = MultiModalEmbedding.call(
                model=self.model,
                input=[item],
                api_key=self.api_key,
                workspace=self.workspace,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            return _map_dashscope_exception(exc)

        if int(getattr(response, "status_code", 0) or 0) != 200:
            return _map_dashscope_failure(response)

        try:
            vector = _extract_embedding_vector(getattr(response, "output", None))
        except Exception as exc:
            return ProxyResult(
                ok=False,
                payload=_error_payload(
                    error_code="SERVER_PROVIDER_UNAVAILABLE",
                    provider="dashscope",
                    message=str(exc),
                    retryable=True,
                    provider_code=getattr(response, "code", None),
                    provider_request_id=getattr(response, "request_id", None),
                    provider_status="invalid_response",
                ),
            )

        return ProxyResult(
            ok=True,
            payload={
                "vector": vector,
                "vector_dim": len(vector),
                "vector_ref": getattr(response, "request_id", None) or "dashscope_embedding",
                "provider": "dashscope",
                "provider_request_id": getattr(response, "request_id", None),
                "provider_status": "ok",
                "model": self.model,
                "modality": modality,
                "usage": getattr(response, "usage", None),
            },
        )

    def _build_item(self, content: str, *, modality: str) -> MultiModalEmbeddingItemImage | MultiModalEmbeddingItemText:
        if modality == "image":
            return MultiModalEmbeddingItemImage(image=_normalize_image_input(content), factor=1.0)
        if modality == "text":
            return MultiModalEmbeddingItemText(text=_normalize_text_input(content), factor=1.0)
        raise ValueError(f"unsupported embedding modality: {modality}")


@dataclass(slots=True)
class AliyunDashVectorAdapter(VectorSearchAdapter):
    api_key: str
    endpoint: str
    collection_name: str
    embedding_adapter: EmbeddingAdapter
    metric: str = "cosine"
    timeout_seconds: float = 10.0
    auto_create_collection: bool = True
    _client: Client | None = field(default=None, init=False, repr=False)
    _collection: Collection | None = field(default=None, init=False, repr=False)
    _collection_dimension: int | None = field(default=None, init=False, repr=False)

    def upsert(
        self,
        documents: Sequence[dict[str, Any]],
        *,
        user_id: str,
        project_id: str,
    ) -> ProxyResult:
        normalized_user_id = user_id.strip()
        normalized_project_id = project_id.strip()
        if not normalized_user_id or not normalized_project_id:
            return ProxyResult(
                ok=False,
                payload=_error_payload(
                    error_code="SERVER_VECTOR_FILTER_INVALID",
                    provider="dashvector",
                    message="user_id and project_id are required for vector upsert.",
                    retryable=False,
                    provider_status="invalid_scope",
                ),
            )
        if not documents:
            return ProxyResult(
                ok=True,
                payload={
                    "upserted": 0,
                    "provider": "dashvector",
                    "provider_status": "noop",
                    "collection": self.collection_name,
                },
            )

        try:
            docs, dimension = self._build_docs(documents, user_id=normalized_user_id, project_id=normalized_project_id)
            collection = self._get_collection(expected_dimension=dimension)
            partition_name = self._ensure_partition(collection, normalized_user_id)
            response = collection.upsert(docs, partition=partition_name)
            return _map_dashvector_response(
                response,
                success_payload={
                    "upserted": len(docs),
                    "collection": self.collection_name,
                    "partition": partition_name,
                    "project_id": normalized_project_id,
                    "user_id": normalized_user_id,
                },
            )
        except Exception as exc:
            return self._map_exception(exc)

    def search(self, query: str, *, top_k: int, filters: dict[str, Any]) -> ProxyResult:
        normalized_filters = dict(filters)
        user_id = str(normalized_filters.get("user_id") or "").strip()
        if not user_id:
            return ProxyResult(
                ok=False,
                payload=_error_payload(
                    error_code="SERVER_VECTOR_FILTER_INVALID",
                    provider="dashvector",
                    message="user_id filter is required for semantic search.",
                    retryable=False,
                    provider_status="invalid_scope",
                ),
            )

        query_embedding = self.embedding_adapter.embed(query, modality="text")
        if not query_embedding.ok:
            return query_embedding

        try:
            vector = [float(value) for value in query_embedding.payload["vector"]]
            collection = self._get_collection(expected_dimension=len(vector))
            partition_name = _sanitize_partition_name(user_id)
            response = collection.query(
                vector,
                topk=max(1, int(top_k)),
                filter=_build_dashvector_filter(normalized_filters),
                partition=partition_name,
                output_fields=["user_id", "project_id", "clip_id", "asset_id", "description", "start_ms", "end_ms", "score"],
            )
            if response.code != DashVectorCode.Success:
                return _map_dashvector_response(response, success_payload={})
            hits = [self._doc_to_hit(doc) for doc in list(getattr(response, "output", None) or [])]
            return ProxyResult(
                ok=True,
                payload={
                    "query": query,
                    "filters": normalized_filters,
                    "hits": hits,
                    "provider": "dashvector",
                    "provider_request_id": getattr(response, "request_id", None),
                    "provider_status": "ok",
                    "collection": self.collection_name,
                    "partition": partition_name,
                    "usage": getattr(response, "usage", None),
                },
            )
        except Exception as exc:
            return self._map_exception(exc)

    def _build_docs(
        self,
        documents: Sequence[dict[str, Any]],
        *,
        user_id: str,
        project_id: str,
    ) -> tuple[list[Doc], int]:
        docs: list[Doc] = []
        dimension: int | None = None
        for raw_document in documents:
            vector = raw_document.get("vector")
            if not isinstance(vector, list) or not vector:
                raise ValueError("vector is required for DashVector upsert")
            if dimension is None:
                dimension = len(vector)
            elif len(vector) != dimension:
                raise ValueError("all vectors in a batch must share the same dimension")
            clip_id = str(raw_document.get("clip_id") or "").strip()
            asset_id = str(raw_document.get("asset_id") or "").strip()
            if not clip_id or not asset_id:
                raise ValueError("clip_id and asset_id are required for DashVector upsert")
            doc_id = f"{user_id}:{project_id}:{clip_id}"
            fields = {
                "user_id": user_id,
                "project_id": project_id,
                "clip_id": clip_id,
                "asset_id": asset_id,
                "description": str(raw_document.get("description") or ""),
                "start_ms": int(raw_document.get("start_ms") or 0),
                "end_ms": int(raw_document.get("end_ms") or 0),
                "score": float(raw_document.get("score") or 0.0),
            }
            docs.append(Doc(id=doc_id, vector=[float(value) for value in vector], fields=fields))
        return docs, int(dimension or 0)

    def _get_collection(self, *, expected_dimension: int) -> Collection:
        if self._collection is not None:
            if self._collection_dimension is not None and expected_dimension != self._collection_dimension:
                raise ValueError(
                    f"DashVector collection dimension mismatch: expected {self._collection_dimension}, got {expected_dimension}"
                )
            return self._collection

        client = self._get_client()
        collection = client.get(self.collection_name)
        if collection.code != DashVectorCode.Success:
            if not self.auto_create_collection:
                raise RuntimeError(f"DashVector collection unavailable: {collection.message}")
            create_response = client.create(
                self.collection_name,
                dimension=expected_dimension,
                metric=self.metric,
                fields_schema={
                    "user_id": str,
                    "project_id": str,
                    "clip_id": str,
                    "asset_id": str,
                    "description": str,
                    "start_ms": int,
                    "end_ms": int,
                    "score": float,
                },
                timeout=30,
            )
            if create_response.code != DashVectorCode.Success:
                raise RuntimeError(f"DashVector create collection failed: {create_response.message}")
            collection = client.get(self.collection_name)
            if collection.code != DashVectorCode.Success:
                raise RuntimeError(f"DashVector get collection failed: {collection.message}")

        self._collection = collection
        self._collection_dimension = expected_dimension
        return collection

    def _ensure_partition(self, collection: Collection, user_id: str) -> str:
        partition_name = _sanitize_partition_name(user_id)
        describe_response = collection.describe_partition(partition_name)
        if describe_response.code == DashVectorCode.Success:
            return partition_name
        create_response = collection.create_partition(partition_name, timeout=30)
        if create_response.code != DashVectorCode.Success:
            raise RuntimeError(f"DashVector create partition failed: {create_response.message}")
        return partition_name

    def _get_client(self) -> Client:
        if self._client is None:
            self._client = Client(
                api_key=self.api_key,
                endpoint=self.endpoint,
                timeout=self.timeout_seconds,
            )
        return self._client

    def _doc_to_hit(self, doc: Any) -> dict[str, Any]:
        fields = dict(getattr(doc, "fields", {}) or {})
        return {
            "clip_id": fields.get("clip_id") or getattr(doc, "id", ""),
            "asset_id": fields.get("asset_id"),
            "project_id": fields.get("project_id"),
            "user_id": fields.get("user_id"),
            "description": fields.get("description"),
            "start_ms": fields.get("start_ms"),
            "end_ms": fields.get("end_ms"),
            "score": float(getattr(doc, "score", 0.0) or 0.0),
        }

    def _map_exception(self, exc: Exception) -> ProxyResult:
        if isinstance(exc, DashVectorException):
            message = exc.message
            provider_code = exc.code
            request_id = exc.request_id
        else:
            message = str(exc)
            provider_code = None
            request_id = None
        lowered = message.lower()
        if "quota" in lowered:
            error_code = "SERVER_PROVIDER_QUOTA_EXCEEDED"
            retryable = False
            provider_status = "quota_exceeded"
        elif "throttl" in lowered or "rate" in lowered:
            error_code = "SERVER_PROVIDER_RATE_LIMITED"
            retryable = True
            provider_status = "rate_limited"
        else:
            error_code = "SERVER_PROVIDER_UNAVAILABLE"
            retryable = True
            provider_status = "provider_exception"
        return ProxyResult(
            ok=False,
            payload=_error_payload(
                error_code=error_code,
                provider="dashvector",
                message=message,
                retryable=retryable,
                provider_code=provider_code,
                provider_request_id=request_id,
                provider_status=provider_status,
            ),
        )


def build_embedding_adapter_from_env() -> EmbeddingAdapter | None:
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        return None
    return AliyunEmbeddingAdapter(
        api_key=api_key,
        model=os.getenv("DASHSCOPE_EMBEDDING_MODEL", "qwen3-vl-embedding").strip() or "qwen3-vl-embedding",
        workspace=os.getenv("DASHSCOPE_WORKSPACE", "").strip() or None,
        timeout_seconds=float(os.getenv("DASHSCOPE_TIMEOUT_SECONDS", "30") or 30),
    )


def build_vector_search_adapter_from_env(embedding_adapter: EmbeddingAdapter) -> VectorSearchAdapter | None:
    api_key = os.getenv("DASHVECTOR_API_KEY", "").strip()
    endpoint = os.getenv("DASHVECTOR_ENDPOINT", "").strip()
    collection_name = os.getenv("DASHVECTOR_COLLECTION", "").strip()
    if not api_key or not endpoint or not collection_name:
        return None
    return AliyunDashVectorAdapter(
        api_key=api_key,
        endpoint=endpoint,
        collection_name=collection_name,
        embedding_adapter=embedding_adapter,
        metric=os.getenv("DASHVECTOR_METRIC", "cosine").strip() or "cosine",
        timeout_seconds=float(os.getenv("DASHVECTOR_TIMEOUT_SECONDS", "10") or 10),
        auto_create_collection=os.getenv("DASHVECTOR_AUTO_CREATE_COLLECTION", "true").lower() != "false",
    )
