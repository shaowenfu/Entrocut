from __future__ import annotations

import asyncio
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
from helpers import (
    _bump_draft,
    _chat_history_summary,
    _draft_summary,
    _entity_id,
    _extract_first_json_object,
    _extract_text_content,
    _now_iso,
    _request_id,
    _trimmed,
)
from inspection import inspect_candidate, pick_clip_for_inspect
from patching import apply_edit_draft_patch
from rendering import build_render_plan, render_preview
from retrieval import retrieve_candidates
from schemas import (
    AgentLoopResultModel,
    ChatTarget,
    ClipModel,
    CoreApiError,
    EditDraftModel,
    PlannerDecisionModel,
    ProjectRuntimeState,
    EditDraftPatchModel,
    SUPPORTED_TOOL_NAMES,
    ToolCallModel,
    ToolObservationModel,
)
from store import store

try:
    from core.context import (
        build_goal_state,
        build_planner_context_packet,
        build_planner_system_prompt,
        build_scope_state,
    )
except ModuleNotFoundError:
    from context import (
        build_goal_state,
        build_planner_context_packet,
        build_planner_system_prompt,
        build_scope_state,
    )


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


def _tool_is_enabled(tool_name: str, capabilities: dict[str, Any]) -> bool:
    if tool_name == "read":
        return True
    capability_map = {
        "retrieve": "can_retrieve",
        "inspect": "can_inspect",
        "patch": "can_patch_draft",
        "preview": "can_preview",
    }
    capability_name = capability_map.get(tool_name)
    if capability_name is None:
        return False
    return bool(capabilities.get(capability_name))


def _planner_workspace_state(
    *,
    record: dict[str, Any],
    draft: EditDraftModel,
    runtime_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    planner_record = {
        **record,
        "edit_draft": draft.model_dump(),
        "runtime_state": ProjectRuntimeState.model_validate(runtime_state).model_dump(),
    }
    media_summary = store._derive_media_summary(planner_record)
    store._sync_runtime_retrieval_state(planner_record, media_summary=media_summary)
    capabilities = store._derive_project_capabilities(planner_record, media_summary=media_summary)
    summary_state = store._derive_summary_state(
        planner_record,
        media_summary=media_summary,
        capabilities=capabilities,
    )
    return planner_record, media_summary, capabilities, summary_state


def _seed_loop_runtime_state(
    *,
    record: dict[str, Any],
    prompt: str,
    target: ChatTarget | None,
    draft: EditDraftModel,
) -> dict[str, Any]:
    current_runtime_state = ProjectRuntimeState.model_validate(record.get("runtime_state") or {}).model_dump()
    now = _now_iso()
    goal_state = build_goal_state(prompt=prompt, runtime_goal_state=current_runtime_state.get("goal_state"))
    current_runtime_state["goal_state"].update(
        {
            "brief": goal_state["goal_summary"],
            "open_questions": goal_state["open_questions"],
            "updated_at": now,
        }
    )
    scope_state = build_scope_state(
        target=target.model_dump() if target else None,
        draft_summary=_draft_summary(draft),
        focus_state=current_runtime_state.get("focus_state"),
    )
    current_runtime_state["focus_state"].update(
        {
            "scope_type": scope_state["scope_type"],
            "scene_id": scope_state["selected_scene_id"],
            "shot_id": scope_state["selected_shot_id"],
            "updated_at": now,
        }
    )
    current_runtime_state["conversation_state"].update(
        {
            "pending_questions": goal_state["open_questions"],
            "updated_at": now,
        }
    )
    current_runtime_state["execution_state"].update(
        {
            "agent_run_state": "planning",
            "last_error": None,
            "updated_at": now,
        }
    )
    current_runtime_state["updated_at"] = now
    return current_runtime_state


def _apply_runtime_state_update(
    runtime_state: dict[str, Any],
    runtime_state_update: dict[str, Any],
) -> dict[str, Any]:
    normalized = ProjectRuntimeState.model_validate(runtime_state).model_dump()
    for section in ("goal_state", "focus_state", "conversation_state", "retrieval_state", "execution_state"):
        update_payload = runtime_state_update.get(section)
        if isinstance(update_payload, dict):
            normalized[section].update(update_payload)
    if runtime_state_update.get("updated_at") is not None:
        normalized["updated_at"] = runtime_state_update["updated_at"]
    return ProjectRuntimeState.model_validate(normalized).model_dump()


def _apply_tool_observation_to_runtime_state(
    runtime_state: dict[str, Any],
    observation: ToolObservationModel,
) -> dict[str, Any]:
    runtime_state_update = observation.state_delta.get("runtime_state_update")
    normalized = ProjectRuntimeState.model_validate(runtime_state).model_dump()
    now = _now_iso()
    normalized["execution_state"].update(
        {
            "last_tool_name": observation.tool_name,
            "updated_at": now,
        }
    )
    normalized["updated_at"] = now
    if isinstance(runtime_state_update, dict):
        normalized = _apply_runtime_state_update(normalized, runtime_state_update)
    return normalized


def _build_planner_messages(
    *,
    record: dict[str, Any],
    project_id: str,
    prompt: str,
    draft: EditDraftModel,
    runtime_state: dict[str, Any],
    target: ChatTarget | None,
    iteration: int,
    observations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    planner_record, media_summary, capabilities, summary_state = _planner_workspace_state(
        record=record,
        draft=draft,
        runtime_state=runtime_state,
    )
    context_packet = build_planner_context_packet(
        project_id=project_id,
        iteration=iteration,
        prompt=prompt,
        target=target.model_dump() if target else None,
        project=planner_record["project"],
        summary_state=summary_state,
        runtime_state=planner_record["runtime_state"],
        media_summary=media_summary,
        capabilities=capabilities,
        draft_summary=_draft_summary(draft),
        chat_history_summary=_chat_history_summary(planner_record),
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
    runtime_state: dict[str, Any],
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
            runtime_state=runtime_state,
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
    capabilities: dict[str, Any],
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
        if not _tool_is_enabled(normalized_tool_name, capabilities):
            raise CoreApiError(
                status_code=502,
                code="PLANNER_REQUESTED_BLOCKED_TOOL",
                message="Planner requested a tool that is unavailable under current workspace capabilities.",
                details={
                    "iteration": iteration,
                    "tool_name": normalized_tool_name,
                    "chat_mode": capabilities.get("chat_mode"),
                    "blocking_reasons": capabilities.get("blocking_reasons", []),
                    "draft_version": draft.version,
                },
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
    runtime_state: dict[str, Any],
    capabilities: dict[str, Any],
    access_token: str,
) -> ToolObservationModel:
    tool_call = _build_tool_call_or_raise(decision)
    if not _tool_is_enabled(tool_call.tool_name, capabilities):
        raise CoreApiError(
            status_code=409,
            code="TOOL_NOT_AVAILABLE_IN_CHAT_MODE",
            message="Requested tool is blocked by current chat mode or workspace capabilities.",
            details={
                "project_id": project_id,
                "iteration": iteration,
                "tool_name": tool_call.tool_name,
                "chat_mode": capabilities.get("chat_mode"),
                "blocking_reasons": capabilities.get("blocking_reasons", []),
            },
        )
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
                state_delta={
                    "runtime_state_update": {
                        "execution_state": {"last_tool_name": "read", "updated_at": _now_iso()},
                        "updated_at": _now_iso(),
                    }
                },
            )

        if tool_call.tool_name == "retrieve":
            query = str(tool_call.tool_input.get("query") or "")
            matches = await retrieve_candidates(
                access_token=access_token,
                project_id=project_id,
                query_text=query,
                draft=draft,
                topk=int(tool_call.tool_input.get("topk") or 8),
            )
            matched_clip_ids = [str(item["clip_id"]) for item in matches]
            return ToolObservationModel(
                tool_name="retrieve",
                success=True,
                summary="Retrieved candidate clips from server vector retrieval.",
                output={"query": query, "matches": matches, "matched_clip_ids": matched_clip_ids},
                state_delta={
                    "runtime_state_update": {
                        "retrieval_state": {
                            "last_query": query.strip() or None,
                            "candidate_clip_ids": matched_clip_ids,
                            "candidate_scores": {item["clip_id"]: item["score"] for item in matches},
                            "retrieval_ready": bool(runtime_state.get("retrieval_state", {}).get("retrieval_ready")),
                            "blocking_reason": None,
                            "updated_at": _now_iso(),
                        },
                        "execution_state": {"last_tool_name": "retrieve", "updated_at": _now_iso()},
                        "updated_at": _now_iso(),
                    }
                },
            )

        if tool_call.tool_name == "inspect":
            clip_id = _trimmed(str(tool_call.tool_input.get("clip_id") or ""))
            candidate_clip_ids = runtime_state.get("retrieval_state", {}).get("candidate_clip_ids") or []
            target_clip = pick_clip_for_inspect(clip_id=clip_id, candidate_clip_ids=candidate_clip_ids, clips=draft.clips)
            score_map = runtime_state.get("retrieval_state", {}).get("candidate_scores") or {}
            inspection = inspect_candidate(clip=target_clip, retrieval_score=score_map.get(target_clip.id))
            return ToolObservationModel(
                tool_name="inspect",
                success=True,
                summary="Inspected clip evidence for decision making.",
                output=inspection,
                state_delta={
                    "runtime_state_update": {
                        "retrieval_state": {
                            "candidate_clip_ids": [target_clip.id],
                            "selected_candidate_id": target_clip.id,
                            "inspection_summary": inspection["summary"],
                            "updated_at": _now_iso(),
                        },
                        "execution_state": {"last_tool_name": "inspect", "updated_at": _now_iso()},
                        "updated_at": _now_iso(),
                    }
                },
            )

        if tool_call.tool_name == "patch":
            clip_id = _trimmed(str(tool_call.tool_input.get("clip_id") or "")) or (
                (runtime_state.get("retrieval_state", {}).get("candidate_clip_ids") or [None])[0]
            )
            if not clip_id:
                raise CoreApiError(status_code=422, code="PATCH_INVALID_CLIP", message="Patch requires clip_id.")
            patch_payload = EditDraftPatchModel(
                operations=[
                    {
                        "op": "insert_shot",
                        "clip_id": clip_id,
                    }
                ],
                reasoning_summary="tool.patch generated",
                scope="project",
            )
            next_draft = apply_edit_draft_patch(draft, patch_payload)
            return ToolObservationModel(
                tool_name="patch",
                success=True,
                summary="Patched draft using formal EditDraftPatch pipeline.",
                output={"clip_id": clip_id, "draft_version": next_draft.version},
                state_delta={
                    "draft_update": next_draft.model_dump(),
                    "runtime_state_update": {
                        "focus_state": {
                            "scope_type": "shot",
                            "scene_id": next_draft.selected_scene_id,
                            "shot_id": next_draft.selected_shot_id,
                            "updated_at": _now_iso(),
                        },
                        "conversation_state": {
                            "confirmed_facts": [f"已将片段 {clip_id} 写入草案"],
                            "updated_at": _now_iso(),
                        },
                        "execution_state": {"last_tool_name": "patch", "updated_at": _now_iso()},
                        "updated_at": _now_iso(),
                    },
                },
            )

        if tool_call.tool_name == "preview":
            preview_path = store._workspace_manager.preview_output_path(project_id, "mp4")
            plan = build_render_plan(draft)
            preview_result = await asyncio.to_thread(render_preview, plan, preview_path)
            await store.emit(
                project_id,
                "preview.completed",
                {
                    "draft_version": draft.version,
                    "output_url": preview_result["output_url"],
                    "duration_ms": preview_result["duration_ms"],
                    "render_profile": "preview",
                },
            )
            return ToolObservationModel(
                tool_name="preview",
                success=True,
                summary="Rendered real preview artifact.",
                output=preview_result,
                state_delta={
                    "runtime_state_update": {
                        "execution_state": {"last_tool_name": "preview", "updated_at": _now_iso()},
                        "updated_at": _now_iso(),
                    }
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
    if draft_update is None:
        return draft
    if not isinstance(draft_update, dict):
        raise CoreApiError(
            status_code=502,
            code="TOOL_OBSERVATION_INVALID",
            message="Tool observation has invalid state delta payload.",
            details={"state_delta_keys": sorted(state_delta.keys())[:20]},
        )
    try:
        if "id" in draft_update and "project_id" in draft_update and "shots" in draft_update:
            return EditDraftModel.model_validate(draft_update)
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
    current_runtime_state = _seed_loop_runtime_state(
        record=record,
        prompt=prompt,
        target=target,
        draft=current_draft,
    )
    observations: list[ToolObservationModel] = []
    for iteration in range(1, agent_loop_max_iterations + 1):
        planner_record, media_summary, capabilities, summary_state = _planner_workspace_state(
            record=record,
            draft=current_draft,
            runtime_state=current_runtime_state,
        )
        await _emit_agent_progress(
            project_id,
            phase="planner_context_assembled",
            summary="Planner context assembled.",
            details={
                "iteration": iteration,
                "draft_version": current_draft.version,
                "observation_count": len(observations),
                "chat_mode": capabilities.get("chat_mode"),
                "summary_state": summary_state,
                "retrieval_ready": media_summary.get("retrieval_ready"),
            },
        )
        decision = await _request_server_planner_decision(
            access_token=access_token,
            record=planner_record,
            project_id=project_id,
            prompt=prompt,
            draft=current_draft,
            runtime_state=current_runtime_state,
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
            capabilities=capabilities,
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
            current_runtime_state["conversation_state"].update(
                {
                    "pending_questions": current_runtime_state["goal_state"].get("open_questions", []),
                    "updated_at": _now_iso(),
                }
            )
            current_runtime_state["execution_state"].update(
                {
                    "agent_run_state": "waiting_user"
                    if current_runtime_state["goal_state"].get("open_questions") and not current_draft.shots
                    else "planning",
                    "updated_at": _now_iso(),
                }
            )
            current_runtime_state["updated_at"] = _now_iso()
            await _emit_agent_progress(
                project_id,
                phase="loop_finalized",
                summary="Planner returned a final decision.",
                details={"iteration": iteration, "draft_version": current_draft.version},
            )
            return AgentLoopResultModel(
                final_decision=decision,
                draft=current_draft,
                observations=observations,
                runtime_state=ProjectRuntimeState.model_validate(current_runtime_state),
            )
        await _emit_agent_progress(
            project_id,
            phase="tool_execution_requested",
            summary="Planner requested tool execution.",
            details={
                "iteration": iteration,
                "tool_name": decision.tool_name,
                "tool_input_summary": decision.tool_input_summary,
                "chat_mode": capabilities.get("chat_mode"),
            },
        )
        observation = await _execute_tool_call_todo(
            project_id=project_id,
            iteration=iteration,
            decision=decision,
            draft=current_draft,
            runtime_state=current_runtime_state,
            capabilities=capabilities,
            access_token=access_token,
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
        current_runtime_state = _apply_tool_observation_to_runtime_state(current_runtime_state, observation)
        current_runtime_state["execution_state"].update(
            {
                "agent_run_state": "planning",
                "updated_at": _now_iso(),
            }
        )
        current_runtime_state["updated_at"] = _now_iso()
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
