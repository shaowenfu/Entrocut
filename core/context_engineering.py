from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlannerRuntimeState(BaseModel):
    identity: dict[str, Any]
    goal: dict[str, Any]
    scope: dict[str, Any]
    draft: dict[str, Any]
    tools: dict[str, Any]
    memory: dict[str, Any]
    runtime_capabilities: dict[str, Any]
    trace: dict[str, Any]


class PlannerContextPacket(BaseModel):
    runtime_state: PlannerRuntimeState
    planner_input: dict[str, Any]


def build_agent_identity_state() -> dict[str, Any]:
    return {
        "agent_name": "EntroCut Core Planner",
        "role": "TODO: define soul.md-backed planner identity",
        "core_principles": [
            "TODO: inject stable agent principles from soul.md",
            "TODO: inject editing-first operating rules",
        ],
        "non_goals": [
            "TODO: inject explicit non-goals",
        ],
    }


def build_goal_state(*, prompt: str) -> dict[str, Any]:
    normalized_prompt = prompt.strip()
    return {
        "user_prompt": normalized_prompt,
        "goal_summary": normalized_prompt,
        "status": "TODO: derive structured goal state from chat input",
        "success_criteria": ["TODO: infer success criteria"],
        "open_questions": ["TODO: derive missing information only when necessary"],
    }


def build_scope_state(*, target: dict[str, Any] | None) -> dict[str, Any]:
    target_payload = target or {}
    if target_payload.get("shot_id"):
        scope_type = "shot"
    elif target_payload.get("scene_id"):
        scope_type = "scene"
    else:
        scope_type = "project"
    return {
        "scope_type": scope_type,
        "target": target_payload or None,
        "status": "TODO: upgrade to persisted focus/scope state",
    }


def build_draft_state(*, project: dict[str, Any], draft_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_summary": {
            "title": project.get("title"),
            "workflow_state": project.get("workflow_state"),
        },
        "working_draft_summary": draft_summary,
        "status": "TODO: replace with step-specific working state summary",
    }


def build_tool_capability_state() -> dict[str, Any]:
    return {
        "available_tools": [
            {
                "name": "read",
                "purpose": "Read current workspace and draft state snapshot for planning.",
            },
            {
                "name": "retrieve",
                "purpose": "Retrieve candidate clips from indexed draft/media summaries.",
            },
            {
                "name": "inspect",
                "purpose": "Inspect clip-level details before making patch decisions.",
            },
            {
                "name": "patch",
                "purpose": "Apply bounded edit-draft updates through state deltas.",
            },
            {
                "name": "preview",
                "purpose": "Generate lightweight preview metadata for verification.",
            },
        ],
        "status": "minimal-loop-tools-ready",
    }


def build_working_memory_state(
    *,
    chat_history_summary: list[str],
    tool_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "recent_chat_summary": chat_history_summary,
        "recent_tool_observations": tool_observations,
        "status": "TODO: replace with structured working memory",
    }


def build_runtime_capabilities_state() -> dict[str, Any]:
    return {
        "planner_loop": "implemented",
        "tool_execution": "implemented_minimal",
        "allowed_draft_strategy": ["placeholder_first_cut", "no_change"],
    }


def build_trace_state(*, project_id: str, iteration: int) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "iteration": iteration,
    }


def build_planner_context_packet(
    *,
    project_id: str,
    iteration: int,
    prompt: str,
    target: dict[str, Any] | None,
    project: dict[str, Any],
    draft_summary: dict[str, Any],
    chat_history_summary: list[str],
    tool_observations: list[dict[str, Any]],
) -> PlannerContextPacket:
    runtime_state = PlannerRuntimeState(
        identity=build_agent_identity_state(),
        goal=build_goal_state(prompt=prompt),
        scope=build_scope_state(target=target),
        draft=build_draft_state(project=project, draft_summary=draft_summary),
        tools=build_tool_capability_state(),
        memory=build_working_memory_state(
            chat_history_summary=chat_history_summary,
            tool_observations=tool_observations,
        ),
        runtime_capabilities=build_runtime_capabilities_state(),
        trace=build_trace_state(project_id=project_id, iteration=iteration),
    )
    planner_input = {
        "identity": runtime_state.identity,
        "goal": runtime_state.goal,
        "scope": runtime_state.scope,
        "draft": runtime_state.draft,
        "tools": runtime_state.tools,
        "memory": runtime_state.memory,
        "runtime_capabilities": runtime_state.runtime_capabilities,
        "trace": runtime_state.trace,
    }
    return PlannerContextPacket(runtime_state=runtime_state, planner_input=planner_input)


def build_planner_system_prompt() -> str:
    return (
        "TODO: replace with soul.md-backed planner instructions.\n"
        "TODO: replace with tool usage policy.\n"
        "TODO: replace with context compaction policy.\n"
        "You are the planning layer for EntroCut Core.\n"
        "Decide the next agent step using the provided planner_input JSON.\n"
        "Return exactly one JSON object with these fields:\n"
        '- status: "final" | "requires_tool"\n'
        "- reasoning_summary: short English planning summary\n"
        "- assistant_reply: concise Chinese reply for the user\n"
        "- tool_name: string or null\n"
        "- tool_input_summary: string or null\n"
        '- draft_strategy: "placeholder_first_cut" | "no_change"\n'
        "Do not return markdown, code fences, or extra prose."
    )
