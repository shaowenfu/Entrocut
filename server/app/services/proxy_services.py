from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.contracts import EmbeddingAdapter, LlmAdapter, ProxyResult, VectorSearchAdapter


@dataclass(slots=True)
class LLMProxyService:
    adapter: LlmAdapter

    def plan_edit(self, prompt: str, *, context: dict[str, Any]) -> ProxyResult:
        return self.adapter.plan(prompt, context=context)


@dataclass(slots=True)
class EmbeddingProxyService:
    adapter: EmbeddingAdapter

    def embed_frame_sheet(self, image_b64: str) -> ProxyResult:
        return self.adapter.embed(image_b64)


@dataclass(slots=True)
class VectorSearchService:
    adapter: VectorSearchAdapter

    def semantic_search(self, query: str, *, top_k: int, filters: dict[str, Any]) -> ProxyResult:
        return self.adapter.search(query, top_k=top_k, filters=filters)


@dataclass(slots=True)
class UsageQuotaService:
    def get_workspace_capabilities(self) -> dict[str, Any]:
        return {
            "embedding": "mock_enabled",
            "vector_search": "mock_enabled",
            "llm": "mock_enabled",
        }

