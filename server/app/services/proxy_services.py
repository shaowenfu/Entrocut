from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.contracts import EmbeddingAdapter, LlmAdapter, ProxyResult, VectorSearchAdapter
from app.repositories.usage_repository import UsageRepositoryShell


def _provider_failure(
    *,
    error_code: str,
    provider: str,
    message: str,
    retryable: bool,
    provider_status: str,
) -> ProxyResult:
    return ProxyResult(
        ok=False,
        payload={
            "error_code": error_code,
            "provider": provider,
            "message": message,
            "retryable": retryable,
            "provider_status": provider_status,
        },
    )


@dataclass(slots=True)
class LLMProxyService:
    adapter: LlmAdapter

    def plan_edit(self, prompt: str, *, context: dict[str, Any]) -> ProxyResult:
        result = self.adapter.plan(prompt, context=context)
        fallback_summary = f"mock_llm:{prompt[:64]}" if prompt.strip() else "mock_llm:empty_prompt"
        return ProxyResult(
            ok=result.ok,
            payload=normalize_plan_payload(result.payload, fallback_summary=fallback_summary),
        )


@dataclass(slots=True)
class EmbeddingProxyService:
    adapter: EmbeddingAdapter
    usage_repository: UsageRepositoryShell | None = None

    def embed_frame_sheet(self, image_b64: str, *, user_id: str | None = None) -> ProxyResult:
        if user_id and self.usage_repository is not None:
            quota = self.usage_repository.consume(user_id, "embedding")
            if not quota["allowed"]:
                return _provider_failure(
                    error_code=quota["error_code"],
                    provider="quota_guard",
                    message=quota["message"],
                    retryable=bool(quota["retryable"]),
                    provider_status=str(quota["provider_status"]),
                )
        return self.adapter.embed(image_b64, modality="image")

    def embed_query(self, query: str, *, user_id: str | None = None) -> ProxyResult:
        if user_id and self.usage_repository is not None:
            quota = self.usage_repository.consume(user_id, "embedding")
            if not quota["allowed"]:
                return _provider_failure(
                    error_code=quota["error_code"],
                    provider="quota_guard",
                    message=quota["message"],
                    retryable=bool(quota["retryable"]),
                    provider_status=str(quota["provider_status"]),
                )
        return self.adapter.embed(query, modality="text")


@dataclass(slots=True)
class VectorSearchService:
    adapter: VectorSearchAdapter
    usage_repository: UsageRepositoryShell | None = None

    def semantic_search(self, query: str, *, top_k: int, filters: dict[str, Any]) -> ProxyResult:
        normalized_filters = self._build_scoped_filters(filters)
        user_id = normalized_filters.get("user_id", "")
        if not user_id:
            return _provider_failure(
                error_code="SERVER_VECTOR_FILTER_INVALID",
                provider="vector_search_service",
                message="user_id filter is required for semantic search.",
                retryable=False,
                provider_status="invalid_scope",
            )
        if self.usage_repository is not None:
            quota = self.usage_repository.consume(user_id, "vector_search")
            if not quota["allowed"]:
                return _provider_failure(
                    error_code=quota["error_code"],
                    provider="quota_guard",
                    message=quota["message"],
                    retryable=bool(quota["retryable"]),
                    provider_status=str(quota["provider_status"]),
                )
        return self.adapter.search(query, top_k=top_k, filters=normalized_filters)

    def upsert_clips(
        self,
        clips: list[dict[str, Any]],
        *,
        user_id: str,
        project_id: str,
    ) -> ProxyResult:
        normalized_user_id = user_id.strip()
        normalized_project_id = project_id.strip()
        if not normalized_user_id or not normalized_project_id:
            return _provider_failure(
                error_code="SERVER_VECTOR_FILTER_INVALID",
                provider="vector_search_service",
                message="user_id and project_id are required for vector upsert.",
                retryable=False,
                provider_status="invalid_scope",
            )
        normalized_clips = []
        for clip in clips:
            normalized_clip = dict(clip)
            normalized_clip["user_id"] = normalized_user_id
            normalized_clip["project_id"] = normalized_project_id
            normalized_clips.append(normalized_clip)
        return self.adapter.upsert(
            normalized_clips,
            user_id=normalized_user_id,
            project_id=normalized_project_id,
        )

    @staticmethod
    def _build_scoped_filters(filters: dict[str, Any]) -> dict[str, Any]:
        raw_filters = dict(filters)
        user_id = str(raw_filters.get("user_id") or "").strip()
        scoped_filters = {key: value for key, value in raw_filters.items() if key != "user_id"}
        if user_id:
            scoped_filters["user_id"] = user_id
        return scoped_filters


@dataclass(slots=True)
class UsageQuotaService:
    usage_repository: UsageRepositoryShell
    embedding_mode: str
    vector_search_mode: str

    def get_workspace_capabilities(self, user_id: str | None = None) -> dict[str, Any]:
        quota_state = self.usage_repository.get_quota_state(user_id or "anonymous")
        return {
            "embedding": self.embedding_mode,
            "vector_search": self.vector_search_mode,
            "llm": "mock_enabled",
            "quota_state": quota_state["quota_state"],
            "quota_limits": quota_state["limits"],
        }


def normalize_plan_payload(payload: dict[str, Any] | None, *, fallback_summary: str) -> dict[str, Any]:
    raw_payload = payload if isinstance(payload, dict) else {}
    normalized_payload = dict(raw_payload)
    normalized_payload["reasoning_summary"] = _normalize_reasoning_summary(
        raw_payload.get("reasoning_summary"),
        fallback_summary=fallback_summary,
    )
    normalized_payload["ops"] = _normalize_operations(raw_payload.get("ops"))
    normalized_payload["storyboard_scenes"] = _normalize_storyboard_scenes(raw_payload.get("storyboard_scenes"))
    return normalized_payload


def _normalize_reasoning_summary(raw_summary: Any, *, fallback_summary: str) -> str:
    summary = str(raw_summary).strip() if raw_summary is not None else ""
    return summary or fallback_summary


def _normalize_operations(raw_ops: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_ops, list):
        return []
    normalized_ops: list[dict[str, Any]] = []
    for item in raw_ops:
        if isinstance(item, dict):
            normalized_ops.append(dict(item))
    return normalized_ops


def _normalize_storyboard_scenes(raw_scenes: Any) -> list[dict[str, str]]:
    if not isinstance(raw_scenes, list):
        return []
    normalized_scenes: list[dict[str, str]] = []
    for index, scene in enumerate(raw_scenes, start=1):
        if not isinstance(scene, dict):
            continue
        normalized_scenes.append(
            {
                "id": _normalize_scene_field(scene.get("id"), fallback=f"scene_{index}"),
                "title": _normalize_scene_field(scene.get("title"), fallback=f"Scene {index}"),
                "duration": _normalize_scene_field(scene.get("duration"), fallback="4s"),
                "intent": _normalize_scene_field(scene.get("intent"), fallback="Keep edit intent stable."),
            }
        )
    return normalized_scenes


def _normalize_scene_field(raw_value: Any, *, fallback: str) -> str:
    value = str(raw_value).strip() if raw_value is not None else ""
    return value or fallback
