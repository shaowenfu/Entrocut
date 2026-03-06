from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class ServerGatewayResponse:
    ok: bool
    payload: dict[str, Any]


class ServerGateway(Protocol):
    def warmup_launchpad(self, prompt: str, *, project_id: str) -> ServerGatewayResponse: ...

    def plan_chat(self, prompt: str, *, project_id: str, context: dict[str, Any]) -> ServerGatewayResponse: ...

    def embed_frame_sheet(self, image_b64: str, *, project_id: str) -> ServerGatewayResponse: ...

    def search_vectors(self, query: str, *, project_id: str) -> ServerGatewayResponse: ...


class MockServerGateway:
    def warmup_launchpad(self, prompt: str, *, project_id: str) -> ServerGatewayResponse:
        return ServerGatewayResponse(
            ok=True,
            payload={
                "project_id": project_id,
                "intent_summary": prompt[:80],
                "priority_subjects": ["action", "wide shot", "close-up"],
            },
        )

    def plan_chat(self, prompt: str, *, project_id: str, context: dict[str, Any]) -> ServerGatewayResponse:
        return ServerGatewayResponse(
            ok=True,
            payload={
                "project_id": project_id,
                "reasoning_summary": f"mock_plan:{prompt[:48]}",
                "context": context,
            },
        )

    def embed_frame_sheet(self, image_b64: str, *, project_id: str) -> ServerGatewayResponse:
        return ServerGatewayResponse(
            ok=True,
            payload={
                "project_id": project_id,
                "vector_dim": 1024,
                "vector_ref": f"mock-vector-{len(image_b64)}",
            },
        )

    def search_vectors(self, query: str, *, project_id: str) -> ServerGatewayResponse:
        return ServerGatewayResponse(
            ok=True,
            payload={
                "project_id": project_id,
                "query": query,
                "hits": [
                    {"clip_id": "mock_clip_1", "score": 0.92},
                    {"clip_id": "mock_clip_2", "score": 0.85},
                ],
            },
        )

