from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(slots=True)
class ProxyResult:
    ok: bool
    payload: dict[str, Any]


class LlmAdapter(Protocol):
    def plan(self, prompt: str, *, context: dict[str, Any]) -> ProxyResult: ...


class EmbeddingAdapter(Protocol):
    def embed(self, content: str, *, modality: str = "image") -> ProxyResult: ...


class VectorSearchAdapter(Protocol):
    def upsert(
        self,
        documents: Sequence[dict[str, Any]],
        *,
        user_id: str,
        project_id: str,
    ) -> ProxyResult: ...

    def search(self, query: str, *, top_k: int, filters: dict[str, Any]) -> ProxyResult: ...
