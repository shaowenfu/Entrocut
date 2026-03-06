from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class ProxyResult:
    ok: bool
    payload: dict[str, Any]


class LlmAdapter(Protocol):
    def plan(self, prompt: str, *, context: dict[str, Any]) -> ProxyResult: ...


class EmbeddingAdapter(Protocol):
    def embed(self, image_b64: str) -> ProxyResult: ...


class VectorSearchAdapter(Protocol):
    def search(self, query: str, *, top_k: int, filters: dict[str, Any]) -> ProxyResult: ...

