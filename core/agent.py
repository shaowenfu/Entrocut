from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from config import (
    DEFAULT_BYOK_BASE_URL,
    SERVER_BASE_URL,
    SERVER_CHAT_MODEL,
    SERVER_CHAT_TIMEOUT_SECONDS,
)
from core.context import build_planner_context_packet, build_planner_system_prompt
from helpers import (
    _bump_draft,
    _chat_history_summary,
    _draft_summary,
    _entity_id,
    _extract_first_json_object,
    _extract_text_content,
    _request_id,
    _trimmed,
)
from schemas import (
    AgentLoopResultModel,
    ChatTarget,
    ClipModel,
    CoreApiError,
    EditDraftModel,
    PlannerDecisionModel,
    SceneModel,
    ShotModel,
    SUPPORTED_TOOL_NAMES,
    ToolCallModel,
    ToolObservationModel,
)
from store import store


async def _emit_agent_progress(
    project_id: str,
    *,
    phase: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> None:
    await store.emit(
        project_id,
        "agent.step.updated",
        {
            "phase": phase,
            "summary": summary,
            "details": details or {},
        },
    )


def _build_planner_messages(
    *,
    record: dict[str, Any],
    project_id: str,
    prompt: str,
    draft: EditDraftModel,
    target: ChatTarget | None,
    iteration: int,
    observations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    context_packet = build_planner_context_packet(
        project_id=project_id,
        iteration=iteration,
        prompt=prompt,
        target=target.model_dump() if target else None,
        project=record["project"],
        draft_summary=_draft_summary(draft),
        chat_history_summary=_chat_history_summary(record),
        tool_observations=observations or [],
    )
    system_prompt = build_planner_system_prompt()
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(context_packet.planner_input, ensure_ascii=False),
        },
    ]


async def _request_server_planner_decision(
    *,
    access_token: str,
    record: dict[str, Any],
    project_id: str,
    prompt: str,
    draft: EditDraftModel,
    target: ChatTarget | None,
    model: str | None,
    routing_mode: str,
    byok_key: str | None,
    byok_base_url: str | None,
    iteration: int,
    observations: list[dict[str, Any]] | None = None,
) -> PlannerDecisionModel:
    payload = {
        "model": model.strip() if isinstance(model, str) and model.strip() else SERVER_CHAT_MODEL,
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 600,
        "messages": _build_planner_messages(
            record=record,
            project_id=project_id,
            prompt=prompt,
            draft=draft,
            target=target,
            iteration=iteration,
            observations=observations,
        ),
    }

    request_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Request-ID": _request_id(),
    }
    if routing_mode == "BYOK":
        normalized_key = (byok_key or "").strip()
        if not normalized_key:
            raise CoreApiError(
                status_code=422,
                code="BYOK_KEY_REQUIRED",
                message="X-BYOK-Key is required when X-Routing-Mode is BYOK.",
            )
        base_url = (byok_base_url or DEFAULT_BYOK_BASE_URL).rstrip("/")
        endpoint_url = f"{base_url}/v1/chat/completions"
        request_headers["Authorization"] = f"Bearer {normalized_key}"
    else:
        endpoint_url = f"{SERVER_BASE_URL}/v1/chat/completions"
        request_headers["Authorization"] = f"Bearer {access_token}"

    async with httpx.AsyncClient(timeout=SERVER_CHAT_TIMEOUT_SECONDS) as client:
        response = await client.post(endpoint_url, json=payload, headers=request_headers)

    if response.status_code == 401:
        raise CoreApiError(
            status_code=401,
            code="AUTH_SESSION_EXPIRED",
            message="Core auth session is expired. Refresh login in client and resync token.",
            details={"server_status": 401},
        )
    if response.status_code == 403:
        raise CoreApiError(
            status_code=403,
            code="AUTH_SESSION_FORBIDDEN",
            message="The current user is not allowed to call server planner proxy.",
            details={"server_status": 403},
        )
    if response.status_code >= 400:
        details: dict[str, Any] = {"server_status": response.status_code}
        try:
            body = response.json()
            if isinstance(body, dict):
                details["server_error"] = body
        except Exception:
            details["server_error_text"] = response.text[:400]
        raise CoreApiError(
            status_code=502,
            code="SERVER_PLANNER_PROXY_FAILED",
            message="Server planner proxy rejected the request.",
            details=details,
        )

    body = response.json()
    choices = body.get("choices") if isinstance(body, dict) else None
    message = choices[0].get("message") if isinstance(choices, list) and choices else None
    content = _extract_text_content(message.get("content") if isinstance(message, dict) else None)
    if not content:
        raise CoreApiError(
            status_code=502,
            code="SERVER_PLANNER_PROXY_EMPTY",
            message="Server planner proxy returned an empty assistant message.",
        )
    json_payload = _extract_first_json_object(content)
    if not json_payload:
        raise CoreApiError(
            status_code=502,
            code="PLANNER_DECISION_INVALID",
            message="Planner response did not contain a JSON decision object.",
            details={"raw_content": content[:400]},
        )
    try:
        parsed = json.loads(json_payload)
    except json.JSONDecodeError as exc:
        raise CoreApiError(
            status_code=502,
            code="PLANNER_DECISION_INVALID",
            message="Planner response returned malformed JSON.",
            details={"raw_content": json_payload[:400]},
        ) from exc
    try:
        return PlannerDecisionModel.model_validate(parsed)
    except ValidationError as exc:
        raise CoreApiError(
            status_code=502,
            code="PLANNER_DECISION_INVALID",
            message="Planner response failed schema validation.",
            details={"validation_errors": exc.errors()},
        ) from exc


def _validate_planner_decision(
    decision: PlannerDecisionModel,
    *,
    iteration: int,
    draft: EditDraftModel,
) -> PlannerDecisionModel:
    if decision.status == "requires_tool":
        normalized_tool_name = _trimmed(decision.tool_name)
        if not normalized_tool_name:
            raise CoreApiError(
                status_code=502,
                code="PLANNER_DECISION_INVALID",
                message="Planner requested tool execution without a tool name.",
                details={"iteration": iteration, "draft_version": draft.version},
            )
        if normalized_tool_name not in SUPPORTED_TOOL_NAMES:
            raise CoreApiError(
                status_code=502,
                code="TOOL_NAME_NOT_SUPPORTED",
                message="Planner requested a tool that is not supported in Core loop.",
                details={"iteration": iteration, "tool_name": normalized_tool_name},
            )
    return decision


def _should_continue_agent_loop(*, decision: PlannerDecisionModel) -> bool:
    return decision.status == "requires_tool"


def _parse_tool_input_summary(tool_input_summary: str | None) -> dict[str, Any]:
    normalized = _trimmed(tool_input_summary)
    if not normalized:
        return {}
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return {"query": normalized}
    return parsed if isinstance(parsed, dict) else {"query": normalized}


def _build_tool_call_or_raise(decision: PlannerDecisionModel) -> ToolCallModel:
    normalized_tool_name = _trimmed(decision.tool_name)
    if not normalized_tool_name:
        raise CoreApiError(
            status_code=502,
            code="PLANNER_DECISION_INVALID",
            message="Planner requested tool execution without a tool name.",
        )
    try:
        return ToolCallModel(
            tool_name=normalized_tool_name,  # type: ignore[arg-type]
            tool_input=_parse_tool_input_summary(decision.tool_input_summary),
        )
    except ValidationError as exc:
        raise CoreApiError(
            status_code=502,
            code="TOOL_INPUT_INVALID",
            message="Planner tool input is invalid for execution.",
            details={"validation_errors": exc.errors()},
        ) from exc


async def _execute_tool_call_todo(
    *,
    project_id: str,
    iteration: int,
    decision: PlannerDecisionModel,
    draft: EditDraftModel,
) -> ToolObservationModel:
    tool_call = _build_tool_call_or_raise(decision)
    try:
        if tool_call.tool_name == "read":
            output = {
                "draft_summary": _draft_summary(draft),
                "query": tool_call.tool_input.get("query"),
            }
            return ToolObservationModel(
                tool_name="read",
                success=True,
                summary="Read current draft state for planner.",
                output=output,
            )

        if tool_call.tool_name == "retrieve":
            query = str(tool_call.tool_input.get("query") or "").lower()
            matched_clip_ids = [
                clip.id
                for clip in draft.clips
                if not query
                or query in clip.visual_desc.lower()
                or any(query in tag.lower() for tag in clip.semantic_tags)
            ][:5]
            return ToolObservationModel(
                tool_name="retrieve",
                success=True,
                summary="Retrieved candidate clips from local draft catalog.",
                output={"query": query, "matched_clip_ids": matched_clip_ids},
            )

        if tool_call.tool_name == "inspect":
            clip_id = _trimmed(str(tool_call.tool_input.get("clip_id") or ""))
            target_clip = next((clip for clip in draft.clips if clip.id == clip_id), None)
            if target_clip is None and draft.clips:
                target_clip = draft.clips[0]
            if target_clip is None:
                raise CoreApiError(
                    status_code=502,
                    code="TOOL_EXECUTION_FAILED",
                    message="Inspect tool could not find any clip in draft.",
                    details={"project_id": project_id, "iteration": iteration},
                )
            return ToolObservationModel(
                tool_name="inspect",
                success=True,
                summary="Inspected clip details for reasoning.",
                output={"clip": target_clip.model_dump()},
            )

        if tool_call.tool_name == "patch":
            clip_id = _trimmed(str(tool_call.tool_input.get("clip_id") or ""))
            target_clip = next((clip for clip in draft.clips if clip.id == clip_id), None)
            if target_clip is None and draft.clips:
                target_clip = draft.clips[0]
            if target_clip is None:
                raise CoreApiError(
                    status_code=502,
                    code="TOOL_EXECUTION_FAILED",
                    message="Patch tool requires at least one clip to create a shot.",
                    details={"project_id": project_id, "iteration": iteration},
                )
            next_order = len(draft.shots)
            shot = ShotModel(
                id=_entity_id("shot"),
                clip_id=target_clip.id,
                source_in_ms=target_clip.source_start_ms,
                source_out_ms=min(target_clip.source_end_ms, target_clip.source_start_ms + 4000),
                order=next_order,
                enabled=True,
                label=f"Patched Shot {next_order + 1}",
                intent="tool.patch generated",
                note=None,
                locked_fields=[],
            )
            scene = SceneModel(
                id=_entity_id("scene"),
                shot_ids=[shot.id],
                order=len(draft.scenes or []),
                enabled=True,
                label=shot.label,
                intent=shot.intent,
                note=None,
                locked_fields=[],
            )
            return ToolObservationModel(
                tool_name="patch",
                success=True,
                summary="Patched draft with one additional shot from selected clip.",
                output={"clip_id": target_clip.id, "shot_id": shot.id},
                state_delta={
                    "draft_update": {
                        "shots": [*draft.shots, shot],
                        "scenes": [*(draft.scenes or []), scene],
                        "selected_shot_id": shot.id,
                        "selected_scene_id": scene.id,
                        "status": "ready",
                    }
                },
            )

        if tool_call.tool_name == "preview":
            return ToolObservationModel(
                tool_name="preview",
                success=True,
                summary="Generated lightweight preview metadata.",
                output={
                    "shot_count": len(draft.shots),
                    "scene_count": len(draft.scenes or []),
                    "estimated_duration_ms": sum(max(0, shot.source_out_ms - shot.source_in_ms) for shot in draft.shots),
                },
            )
    except CoreApiError:
        raise
    except Exception as exc:
        raise CoreApiError(
            status_code=502,
            code="TOOL_EXECUTION_FAILED",
            message="Tool execution failed unexpectedly.",
            details={"tool_name": tool_call.tool_name, "error": str(exc)},
        ) from exc

    raise CoreApiError(
        status_code=502,
        code="TOOL_NAME_NOT_SUPPORTED",
        message="Tool is not supported by current loop implementation.",
        details={"tool_name": tool_call.tool_name},
    )


def _apply_tool_observation_to_draft_todo(draft: EditDraftModel, observation: ToolObservationModel) -> EditDraftModel:
    state_delta = observation.state_delta
    if not state_delta:
        return draft
    draft_update = state_delta.get("draft_update")
    if not isinstance(draft_update, dict):
        raise CoreApiError(
            status_code=502,
            code="TOOL_OBSERVATION_INVALID",
            message="Tool observation has invalid state delta payload.",
            details={"state_delta_keys": sorted(state_delta.keys())[:20]},
        )
    try:
        return _bump_draft(draft, **draft_update)
    except Exception as exc:
        raise CoreApiError(
            status_code=502,
            code="STATE_WRITEBACK_FAILED",
            message="Failed to apply tool state delta to draft.",
            details={"error": str(exc)},
        ) from exc


async def _run_chat_agent_loop(
    *,
    record: dict[str, Any],
    project_id: str,
    access_token: str,
    prompt: str,
    draft: EditDraftModel,
    target: ChatTarget | None,
    model: str | None,
    routing_mode: str,
    byok_key: str | None,
    byok_base_url: str | None,
    agent_loop_max_iterations: int,
) -> AgentLoopResultModel:
    await _emit_agent_progress(
        project_id,
        phase="loop_started",
        summary="Agent loop started.",
        details={"max_iterations": agent_loop_max_iterations},
    )
    current_draft = draft
    observations: list[ToolObservationModel] = []
    for iteration in range(1, agent_loop_max_iterations + 1):
        await _emit_agent_progress(
            project_id,
            phase="planner_context_assembled",
            summary="Planner context assembled.",
            details={
                "iteration": iteration,
                "draft_version": current_draft.version,
                "observation_count": len(observations),
            },
        )
        decision = await _request_server_planner_decision(
            access_token=access_token,
            record=record,
            project_id=project_id,
            prompt=prompt,
            draft=current_draft,
            target=target,
            model=model,
            routing_mode=routing_mode,
            byok_key=byok_key,
            byok_base_url=byok_base_url,
            iteration=iteration,
            observations=[item.model_dump() for item in observations],
        )
        decision = _validate_planner_decision(
            decision,
            iteration=iteration,
            draft=current_draft,
        )
        await _emit_agent_progress(
            project_id,
            phase="planner_decision_received",
            summary="Planner decision received.",
            details={
                "iteration": iteration,
                "status": decision.status,
                "draft_strategy": decision.draft_strategy,
                "tool_name": decision.tool_name,
            },
        )
        if not _should_continue_agent_loop(decision=decision):
            await _emit_agent_progress(
                project_id,
                phase="loop_finalized",
                summary="Planner returned a final decision.",
                details={"iteration": iteration, "draft_version": current_draft.version},
            )
            return AgentLoopResultModel(final_decision=decision, draft=current_draft, observations=observations)
        await _emit_agent_progress(
            project_id,
            phase="tool_execution_requested",
            summary="Planner requested tool execution.",
            details={
                "iteration": iteration,
                "tool_name": decision.tool_name,
                "tool_input_summary": decision.tool_input_summary,
            },
        )
        observation = await _execute_tool_call_todo(
            project_id=project_id,
            iteration=iteration,
            decision=decision,
            draft=current_draft,
        )
        observations.append(observation)
        await _emit_agent_progress(
            project_id,
            phase="tool_observation_recorded",
            summary="Tool observation recorded for replanning.",
            details={
                "iteration": iteration,
                "tool_name": observation.tool_name,
                "success": observation.success,
                "observation_count": len(observations),
            },
        )
        current_draft = _apply_tool_observation_to_draft_todo(current_draft, observation)
        await _emit_agent_progress(
            project_id,
            phase="draft_updated_in_loop",
            summary="Loop draft state updated from tool observation.",
            details={"iteration": iteration, "draft_version": current_draft.version},
        )
    raise CoreApiError(
        status_code=502,
        code="AGENT_LOOP_DID_NOT_FINALIZE",
        message="Planner loop exceeded the iteration budget without producing a final decision.",
        details={"max_iterations": agent_loop_max_iterations},
    )
