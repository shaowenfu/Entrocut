from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.adapters.contracts import ProxyResult


class MockLlmAdapter:
    def plan(self, prompt: str, *, context: dict[str, object]) -> ProxyResult:
        return ProxyResult(
            ok=True,
            payload={
                "reasoning_summary": f"mock_llm:{prompt[:64]}",
                "context": context,
                "ops": [{"op": "mock_plan_generated", "note": "phase3_mock"}],
                "storyboard_scenes": [
                    {
                        "id": "scene_1",
                        "title": "Intent Warmup",
                        "duration": "4s",
                        "intent": "Confirm direction before patch generation.",
                    },
                    {
                        "id": "scene_2",
                        "title": "Rhythm Lift",
                        "duration": "6s",
                        "intent": "Keep pacing aligned with the latest user prompt.",
                    },
                ],
            },
        )


class MockEmbeddingAdapter:
    def embed(self, content: str, *, modality: str = "image") -> ProxyResult:
        seed = f"{modality}:{content}".encode("utf-8")
        digest = hashlib.sha256(seed).digest()
        vector = [round(byte / 255.0, 6) for byte in digest[:16]]
        return ProxyResult(
            ok=True,
            payload={
                "vector_dim": len(vector),
                "vector_ref": f"mock_embedding_{len(content)}",
                "vector": vector,
                "provider": "mock_embedding",
                "provider_status": "ok",
                "modality": modality,
            },
        )


@dataclass(slots=True)
class MockVectorSearchAdapter:
    _docs_by_user: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def upsert(self, documents: list[dict[str, Any]], *, user_id: str, project_id: str) -> ProxyResult:
        scoped_docs: list[dict[str, Any]] = []
        for raw_document in documents:
            doc = dict(raw_document)
            doc["user_id"] = user_id
            doc["project_id"] = project_id
            scoped_docs.append(doc)
        bucket = [doc for doc in self._docs_by_user.get(user_id, []) if doc.get("project_id") != project_id]
        bucket.extend(scoped_docs)
        self._docs_by_user[user_id] = bucket
        return ProxyResult(
            ok=True,
            payload={
                "upserted": len(scoped_docs),
                "provider": "mock_vector_search",
                "provider_status": "ok",
                "user_id": user_id,
                "project_id": project_id,
            },
        )

    def search(self, query: str, *, top_k: int, filters: dict[str, object]) -> ProxyResult:
        user_id = str(filters.get("user_id") or "").strip()
        project_id = str(filters.get("project_id") or "").strip()
        docs = list(self._docs_by_user.get(user_id, []))
        if project_id:
            docs = [doc for doc in docs if doc.get("project_id") == project_id]
        if docs:
            hits = []
            for doc in docs[: max(1, top_k)]:
                text = str(doc.get("description") or doc.get("clip_id") or "")
                score = 0.75 + min(0.24, len(set(query.lower()) & set(text.lower())) / max(1, len(set(query.lower()))))
                hits.append(
                    {
                        "clip_id": doc.get("clip_id"),
                        "asset_id": doc.get("asset_id"),
                        "project_id": doc.get("project_id"),
                        "user_id": doc.get("user_id"),
                        "description": doc.get("description"),
                        "start_ms": doc.get("start_ms"),
                        "end_ms": doc.get("end_ms"),
                        "score": round(score, 4),
                    }
                )
        else:
            hits = [
                {"clip_id": "mock_clip_1", "score": 0.93, "user_id": user_id or "mock_user"},
                {"clip_id": "mock_clip_2", "score": 0.87, "user_id": user_id or "mock_user"},
                {"clip_id": "mock_clip_3", "score": 0.81, "user_id": user_id or "mock_user"},
            ]
        return ProxyResult(
            ok=True,
            payload={
                "query": query,
                "filters": filters,
                "hits": hits[: max(1, top_k)],
                "provider": "mock_vector_search",
                "provider_status": "ok",
            },
        )
