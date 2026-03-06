from __future__ import annotations

from app.adapters.contracts import ProxyResult


class MockLlmAdapter:
    def plan(self, prompt: str, *, context: dict[str, object]) -> ProxyResult:
        return ProxyResult(
            ok=True,
            payload={
                "reasoning_summary": f"mock_llm:{prompt[:64]}",
                "context": context,
                "ops": [{"op": "mock_plan_generated", "note": "phase3_mock"}],
            },
        )


class MockEmbeddingAdapter:
    def embed(self, image_b64: str) -> ProxyResult:
        return ProxyResult(
            ok=True,
            payload={
                "vector_dim": 1024,
                "vector_ref": f"mock_embedding_{len(image_b64)}",
            },
        )


class MockVectorSearchAdapter:
    def search(self, query: str, *, top_k: int, filters: dict[str, object]) -> ProxyResult:
        hits = [
            {"clip_id": "mock_clip_1", "score": 0.93},
            {"clip_id": "mock_clip_2", "score": 0.87},
            {"clip_id": "mock_clip_3", "score": 0.81},
        ]
        return ProxyResult(
            ok=True,
            payload={
                "query": query,
                "filters": filters,
                "hits": hits[: max(1, top_k)],
            },
        )

