from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PlannerRuntimeState(BaseModel):
    identity: dict[str, Any]
    goal: dict[str, Any]
    scope: dict[str, Any]
    project: dict[str, Any]
    draft: dict[str, Any]
    media: dict[str, Any]
    capabilities: dict[str, Any]
    tools: dict[str, Any]
    memory: dict[str, Any]
    runtime_state: dict[str, Any]
    runtime_capabilities: dict[str, Any]
    trace: dict[str, Any]


class PlannerContextPacket(BaseModel):
    runtime_state: PlannerRuntimeState
    planner_input: dict[str, Any]


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def _normalize_string_list(values: list[Any] | None) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        text = _normalize_text(value)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _infer_success_criteria(prompt: str) -> list[str]:
    criteria = ["输出结果应与用户描述目标保持一致"]
    lowered = prompt.lower()
    if any(token in prompt for token in ["开头", "片头", "第一段"]) or "opening" in lowered:
        criteria.append("草案应明确包含开场结构（例如前3-10秒引入）")
    if any(token in prompt for token in ["节奏", "快", "慢"]) or "rhythm" in lowered:
        criteria.append("剪辑节奏应与用户要求匹配")
    if any(token in prompt for token in ["情绪", "氛围", "感觉"]) or "mood" in lowered:
        criteria.append("画面表达的情绪和氛围应可感知")
    return criteria


def _infer_open_questions(prompt: str) -> list[str]:
    questions: list[str] = []
    lowered = prompt.lower()
    if not any(token in prompt for token in ["时长", "秒", "分钟"]) and "duration" not in lowered:
        questions.append("目标片段期望时长尚未明确")
    if not any(token in prompt for token in ["比例", "横屏", "竖屏", "16:9", "9:16"]) and "aspect" not in lowered:
        questions.append("输出画幅与分发平台尚未明确")
    if not any(token in prompt for token in ["音乐", "配乐", "字幕", "旁白"]) and "music" not in lowered:
        questions.append("音频策略（配乐/旁白/字幕）尚未明确")
    return questions


def build_agent_identity_state() -> dict[str, Any]:
    return {
        "agent_name": "EntroCut Core Planner",
        "role": "对话到剪辑的规划层，负责将用户意图转成下一步可执行决策",
        "core_principles": [
            "优先基于结构化 runtime state 做决策，而不是复述原始聊天文本",
            "每一轮只推进最关键的一步，并保证输出可被程序消费",
            "当信息不足时优先澄清关键缺口，避免盲目修改草案",
        ],
        "non_goals": [
            "不直接承担底层媒体处理细节",
            "不跳过工具边界直接伪造执行结果",
        ],
    }


def build_goal_state(*, prompt: str, runtime_goal_state: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_prompt = _normalize_text(prompt)
    runtime_goal = runtime_goal_state or {}
    runtime_open_questions = _normalize_string_list(runtime_goal.get("open_questions"))
    inferred_open_questions = _infer_open_questions(normalized_prompt)
    return {
        "user_intent": normalized_prompt,
        "goal_summary": _normalize_text(str(runtime_goal.get("brief") or normalized_prompt)),
        "constraints": _normalize_string_list(runtime_goal.get("constraints")),
        "preferences": _normalize_string_list(runtime_goal.get("preferences")),
        "success_criteria": _infer_success_criteria(normalized_prompt),
        "open_questions": runtime_open_questions + [
            item for item in inferred_open_questions if item not in runtime_open_questions
        ],
        "goal_source": "runtime_state_then_prompt",
    }


def build_scope_state(
    *,
    target: dict[str, Any] | None,
    draft_summary: dict[str, Any] | None = None,
    focus_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_payload = target or {}
    focus_payload = focus_state or {}
    selected_shot_id = (
        target_payload.get("shot_id")
        or focus_payload.get("shot_id")
        or (draft_summary or {}).get("selected_shot_id")
    )
    selected_scene_id = (
        target_payload.get("scene_id")
        or focus_payload.get("scene_id")
        or (draft_summary or {}).get("selected_scene_id")
    )

    if selected_shot_id:
        scope_type = "shot"
    elif selected_scene_id:
        scope_type = "scene"
    else:
        scope_type = str(focus_payload.get("scope_type") or "project")

    return {
        "scope_type": scope_type,
        "selected_scene_id": selected_scene_id,
        "selected_shot_id": selected_shot_id,
        "target": target_payload or None,
        "derivation": "target_then_runtime_focus_then_draft_selection",
    }


def build_project_state(*, project: dict[str, Any], summary_state: str | None) -> dict[str, Any]:
    return {
        "project_id": project.get("id"),
        "title": project.get("title"),
        "summary_state": summary_state,
        "lifecycle_state": project.get("lifecycle_state"),
    }


def build_draft_state(*, draft_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "working_draft_summary": draft_summary,
        "draft_focus": {
            "draft_version": draft_summary.get("draft_version"),
            "shot_count": draft_summary.get("shot_count"),
            "scene_count": draft_summary.get("scene_count"),
        },
    }


def build_media_state(*, media_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_count": media_summary.get("asset_count", 0),
        "pending_asset_count": media_summary.get("pending_asset_count", 0),
        "processing_asset_count": media_summary.get("processing_asset_count", 0),
        "ready_asset_count": media_summary.get("ready_asset_count", 0),
        "failed_asset_count": media_summary.get("failed_asset_count", 0),
        "total_clip_count": media_summary.get("total_clip_count", 0),
        "indexed_clip_count": media_summary.get("indexed_clip_count", 0),
        "retrieval_ready": bool(media_summary.get("retrieval_ready")),
    }


def build_capabilities_state(*, capabilities: dict[str, Any]) -> dict[str, Any]:
    return {
        "chat_mode": capabilities.get("chat_mode"),
        "can_send_chat": bool(capabilities.get("can_send_chat")),
        "can_retrieve": bool(capabilities.get("can_retrieve")),
        "can_inspect": bool(capabilities.get("can_inspect")),
        "can_patch_draft": bool(capabilities.get("can_patch_draft")),
        "can_preview": bool(capabilities.get("can_preview")),
        "can_export": bool(capabilities.get("can_export")),
        "blocking_reasons": _normalize_string_list(capabilities.get("blocking_reasons")),
    }


def build_tool_capability_state(*, capabilities: dict[str, Any], media_summary: dict[str, Any]) -> dict[str, Any]:
    tool_enabled_map = {
        "read": True,
        "retrieve": bool(capabilities.get("can_retrieve")),
        "inspect": bool(capabilities.get("can_inspect")),
        "patch": bool(capabilities.get("can_patch_draft")),
        "preview": bool(capabilities.get("can_preview")),
    }
    blocking_reasons = _normalize_string_list(capabilities.get("blocking_reasons"))
    default_blocking_reason = blocking_reasons[0] if blocking_reasons else None

    def _tool_descriptor(
        *,
        name: str,
        purpose: str,
        when_to_use: str,
        when_not_to_use: str,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "purpose": purpose,
            "when_to_use": when_to_use,
            "when_not_to_use": when_not_to_use,
            "enabled": tool_enabled_map[name],
            "blocking_reason": None if tool_enabled_map[name] else default_blocking_reason,
        }

    return {
        "available_tools": [
            _tool_descriptor(
                name="read",
                purpose="读取当前工作事实（草案、选区、候选、约束）以避免基于过期信息决策",
                when_to_use="在规划前需要确认当前状态、或发现上下文可能过期时",
                when_not_to_use="仅做自然语言回复且现有上下文已足够时",
            ),
            _tool_descriptor(
                name="retrieve",
                purpose="从素材池召回与当前目标相关的候选片段",
                when_to_use="需要寻找新素材、替换素材或补充候选时",
                when_not_to_use="chat_mode 为 planning_only 或当前无可检索 clip 时",
            ),
            _tool_descriptor(
                name="inspect",
                purpose="对候选进行比较、消歧与质量判断",
                when_to_use="候选存在多个可行项，需要进一步判优时",
                when_not_to_use="尚无候选可比较，或 retrieve 尚不可用时",
            ),
            _tool_descriptor(
                name="patch",
                purpose="将结构化增量修改应用到 EditDraft",
                when_to_use="已形成明确编辑决策并需落盘到草案时",
                when_not_to_use="planning_only 阶段或素材候选仍不足时",
            ),
            _tool_descriptor(
                name="preview",
                purpose="生成可审阅预览以验证当前草案效果",
                when_to_use="需要向用户展示阶段性结果或验证可视化效果时",
                when_not_to_use="草案尚未形成可评估结构时",
            ),
        ],
        "chat_mode": capabilities.get("chat_mode"),
        "tool_policy": (
            "planning_only 时优先澄清需求，只允许低风险操作；"
            "editing 时按 capability 使用完整工具链。"
        ),
        "media_readiness": {
            "asset_count": media_summary.get("asset_count", 0),
            "indexed_clip_count": media_summary.get("indexed_clip_count", 0),
            "retrieval_ready": bool(media_summary.get("retrieval_ready")),
        },
        "status": "capability-gated-tools-ready",
        "source": "workspace_capabilities_and_media_summary",
    }


def build_working_memory_state(
    *,
    chat_history_summary: list[str],
    tool_observations: list[dict[str, Any]],
    runtime_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_payload = runtime_state or {}
    conversation_state = runtime_payload.get("conversation_state") if isinstance(runtime_payload, dict) else {}
    retrieval_state = runtime_payload.get("retrieval_state") if isinstance(runtime_payload, dict) else {}
    recent_decisions = [line for line in chat_history_summary if line.startswith("assistant:")][:3]
    recent_observation_summary = [
        {
            "tool_name": item.get("tool_name"),
            "success": item.get("success"),
            "summary": item.get("summary") or item.get("tool_input_summary"),
        }
        for item in tool_observations[-3:]
    ]
    pending_risks: list[str] = []
    if not tool_observations:
        pending_risks.append("尚无工具观测，决策主要依赖聊天与草案摘要")
    blocking_reason = retrieval_state.get("blocking_reason") if isinstance(retrieval_state, dict) else None
    if isinstance(blocking_reason, str) and blocking_reason:
        pending_risks.append(f"retrieval 当前受阻：{blocking_reason}")

    return {
        "recent_chat_summary": chat_history_summary[-6:],
        "recent_decisions": recent_decisions,
        "recent_tool_observations": recent_observation_summary,
        "pending_risks": pending_risks,
        "open_questions": _normalize_string_list((conversation_state or {}).get("pending_questions")),
        "confirmed_facts": _normalize_string_list((conversation_state or {}).get("confirmed_facts")),
    }


def build_runtime_state_snapshot(runtime_state: dict[str, Any] | None) -> dict[str, Any]:
    payload = runtime_state or {}
    return {
        "goal_state": payload.get("goal_state") or {},
        "focus_state": payload.get("focus_state") or {},
        "conversation_state": payload.get("conversation_state") or {},
        "retrieval_state": payload.get("retrieval_state") or {},
        "execution_state": payload.get("execution_state") or {},
        "updated_at": payload.get("updated_at"),
    }


def build_runtime_capabilities_state(*, capabilities: dict[str, Any]) -> dict[str, Any]:
    return {
        "planner_loop": "implemented",
        "tool_execution": "implemented_minimal",
        "allowed_draft_strategy": ["placeholder_first_cut", "no_change"],
        "chat_mode": capabilities.get("chat_mode"),
        "tool_gating": "workspace_capabilities",
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
    summary_state: str | None,
    runtime_state: dict[str, Any],
    media_summary: dict[str, Any],
    capabilities: dict[str, Any],
    draft_summary: dict[str, Any],
    chat_history_summary: list[str],
    tool_observations: list[dict[str, Any]],
) -> PlannerContextPacket:
    normalized_runtime_state = build_runtime_state_snapshot(runtime_state)
    planner_runtime_state = PlannerRuntimeState(
        identity=build_agent_identity_state(),
        goal=build_goal_state(prompt=prompt, runtime_goal_state=normalized_runtime_state.get("goal_state")),
        scope=build_scope_state(
            target=target,
            draft_summary=draft_summary,
            focus_state=normalized_runtime_state.get("focus_state"),
        ),
        project=build_project_state(project=project, summary_state=summary_state),
        draft=build_draft_state(draft_summary=draft_summary),
        media=build_media_state(media_summary=media_summary),
        capabilities=build_capabilities_state(capabilities=capabilities),
        tools=build_tool_capability_state(capabilities=capabilities, media_summary=media_summary),
        memory=build_working_memory_state(
            chat_history_summary=chat_history_summary,
            tool_observations=tool_observations,
            runtime_state=normalized_runtime_state,
        ),
        runtime_state=normalized_runtime_state,
        runtime_capabilities=build_runtime_capabilities_state(capabilities=capabilities),
        trace=build_trace_state(project_id=project_id, iteration=iteration),
    )
    planner_input = {
        "identity": planner_runtime_state.identity,
        "goal": {
            "goal_summary": planner_runtime_state.goal["goal_summary"],
            "constraints": planner_runtime_state.goal["constraints"],
            "preferences": planner_runtime_state.goal["preferences"],
            "success_criteria": planner_runtime_state.goal["success_criteria"],
            "open_questions": planner_runtime_state.goal["open_questions"],
        },
        "scope": planner_runtime_state.scope,
        "project": planner_runtime_state.project,
        "draft": planner_runtime_state.draft,
        "media": planner_runtime_state.media,
        "capabilities": planner_runtime_state.capabilities,
        "tools": planner_runtime_state.tools,
        "memory": planner_runtime_state.memory,
        "runtime_state": planner_runtime_state.runtime_state,
        "runtime_capabilities": planner_runtime_state.runtime_capabilities,
        "trace": planner_runtime_state.trace,
    }
    return PlannerContextPacket(runtime_state=planner_runtime_state, planner_input=planner_input)


def build_planner_system_prompt() -> str:
    return (
        "[Identity]\n"
        "You are EntroCut Core Planner, responsible for the next best editing decision.\n"
        "[Tool Usage Policy]\n"
        "Use tools only when needed. Respect tools.available_tools[].enabled and capabilities.chat_mode."
        " Prefer read before risky operations. For scope expansion, retrieve first; for candidate judgment, inspect;"
        " for deterministic draft updates, patch; for review output, preview."
        " If chat_mode is planning_only or a tool is disabled, ask clarifying questions instead of requesting that tool.\n"
        "[Context Compaction Policy]\n"
        "Rely on planner_input as the single source of decision context."
        " Treat chat history as summarized memory, not raw transcript.\n"
        "[Output Contract]\n"
        "Return exactly one JSON object with fields:\n"
        '- status: "final" | "requires_tool"\n'
        "- reasoning_summary: short English planning summary\n"
        "- assistant_reply: concise Chinese reply for the user\n"
        "- tool_name: string or null\n"
        "- tool_input_summary: string or null\n"
        '- draft_strategy: "placeholder_first_cut" | "no_change"\n'
        "Do not return markdown, code fences, or extra prose."
    )
