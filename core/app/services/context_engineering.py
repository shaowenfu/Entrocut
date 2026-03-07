from __future__ import annotations

from dataclasses import dataclass
from typing import Any


NO_MEDIA_PROMPT_HINT = "当前没有可用素材，请先引导用户上传视频并给出具体下一步。"


@dataclass(slots=True)
class EngineeredChatRequest:
    prompt: str
    context: dict[str, Any]
    requires_media: bool
    interaction_mode: str


class CoreContextEngineeringShell:
    def build_chat_request(
        self,
        *,
        prompt: str,
        project_id: str,
        user_id: str,
        client_context: dict[str, Any] | None,
        runtime_state: dict[str, Any],
        asset_count: int,
        clip_count: int,
        current_project: dict[str, Any] | None,
    ) -> EngineeredChatRequest:
        normalized_prompt = prompt.strip()
        has_media = asset_count > 0
        workflow_state = str(runtime_state.get("workflow_state") or "prompt_input_required")
        active_task_type = runtime_state.get("active_task_type")
        pending_prompt = runtime_state.get("pending_prompt")
        merged_context = {
            "project_id": project_id,
            "user_id": user_id,
            "workflow_state": workflow_state,
            "active_task_type": active_task_type,
            "pending_prompt_exists": bool(pending_prompt),
            "has_media": has_media,
            "asset_count": asset_count,
            "clip_count": clip_count,
            "client_context": client_context or {},
            "current_project_present": current_project is not None,
            "search_scope": "clip_pool" if clip_count > 0 else "none",
        }
        if has_media:
            return EngineeredChatRequest(
                prompt=normalized_prompt,
                context=merged_context,
                requires_media=False,
                interaction_mode="workspace_chat",
            )
        return EngineeredChatRequest(
            prompt=f"{normalized_prompt}\n\n[system]\n{NO_MEDIA_PROMPT_HINT}",
            context={
                **merged_context,
                "requires_media": True,
                "interaction_mode": "prompt_only",
            },
            requires_media=True,
            interaction_mode="prompt_only",
        )
