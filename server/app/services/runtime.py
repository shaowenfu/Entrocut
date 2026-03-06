from __future__ import annotations

from dataclasses import dataclass

from app.adapters.mock_providers import MockEmbeddingAdapter, MockLlmAdapter, MockVectorSearchAdapter
from app.services.proxy_services import (
    EmbeddingProxyService,
    LLMProxyService,
    UsageQuotaService,
    VectorSearchService,
)


@dataclass(slots=True)
class ServerRuntime:
    llm_proxy: LLMProxyService
    embedding_proxy: EmbeddingProxyService
    vector_search: VectorSearchService
    usage_quota: UsageQuotaService


def build_server_runtime() -> ServerRuntime:
    return ServerRuntime(
        llm_proxy=LLMProxyService(adapter=MockLlmAdapter()),
        embedding_proxy=EmbeddingProxyService(adapter=MockEmbeddingAdapter()),
        vector_search=VectorSearchService(adapter=MockVectorSearchAdapter()),
        usage_quota=UsageQuotaService(),
    )

