from __future__ import annotations

from dataclasses import dataclass

from app.adapters.aliyun_providers import build_embedding_adapter_from_env, build_vector_search_adapter_from_env
from app.adapters.mock_providers import MockEmbeddingAdapter, MockLlmAdapter, MockVectorSearchAdapter
from app.repositories.usage_repository import UsageRepositoryShell
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
    usage_repository = UsageRepositoryShell()
    embedding_adapter = build_embedding_adapter_from_env()
    embedding_mode = "real_enabled" if embedding_adapter is not None else "mock_enabled"
    embedding_proxy = EmbeddingProxyService(
        adapter=embedding_adapter or MockEmbeddingAdapter(),
        usage_repository=usage_repository,
    )

    vector_adapter = None
    if embedding_adapter is not None:
        vector_adapter = build_vector_search_adapter_from_env(embedding_adapter)
    vector_mode = "real_enabled" if vector_adapter is not None else "mock_enabled"
    return ServerRuntime(
        llm_proxy=LLMProxyService(adapter=MockLlmAdapter()),
        embedding_proxy=embedding_proxy,
        vector_search=VectorSearchService(
            adapter=vector_adapter or MockVectorSearchAdapter(),
            usage_repository=usage_repository,
        ),
        usage_quota=UsageQuotaService(
            usage_repository=usage_repository,
            embedding_mode=embedding_mode,
            vector_search_mode=vector_mode,
        ),
    )
