from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


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


def build_goal_state(*, prompt: str) -> dict[str, Any]:
    normalized_prompt = _normalize_text(prompt)
    return {
        "user_intent": normalized_prompt,
        "goal_summary": normalized_prompt,
        "success_criteria": _infer_success_criteria(normalized_prompt),
        "open_questions": _infer_open_questions(normalized_prompt),
    }


def build_scope_state(
    *,
    target: dict[str, Any] | None,
    draft_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_payload = target or {}
    selected_shot_id = target_payload.get("shot_id") or (draft_summary or {}).get("selected_shot_id")
    selected_scene_id = target_payload.get("scene_id") or (draft_summary or {}).get("selected_scene_id")

    if selected_shot_id:
        scope_type = "shot"
    elif selected_scene_id:
        scope_type = "scene"
    else:
        scope_type = "project"

    return {
        "scope_type": scope_type,
        "selected_scene_id": selected_scene_id,
        "selected_shot_id": selected_shot_id,
        "target": target_payload or None,
        "derivation": "heuristic_from_chat_target_and_draft_selection",
    }


def build_draft_state(*, project: dict[str, Any], draft_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_summary": {
            "title": project.get("title"),
            "workflow_state": project.get("workflow_state"),
        },
        "working_draft_summary": draft_summary,
        "draft_focus": {
            "draft_version": draft_summary.get("draft_version"),
            "shot_count": draft_summary.get("shot_count"),
            "scene_count": draft_summary.get("scene_count"),
        },
    }


def build_tool_capability_state() -> dict[str, Any]:
    return {
        "available_tools": [
            {
                "name": "read",
                "purpose": "读取当前工作事实（草案、选区、候选、约束）以避免基于过期信息决策",
                "when_to_use": "在规划前需要确认当前状态、或发现上下文可能过期时",
                "when_not_to_use": "仅做自然语言回复且现有上下文已足够时",
            },
            {
                "name": "retrieve",
                "purpose": "从素材池召回与当前目标相关的候选片段",
                "when_to_use": "需要寻找新素材、替换素材或补充候选时",
                "when_not_to_use": "当前候选已充分且只需做局部排序判断时",
            },
            {
                "name": "inspect",
                "purpose": "对候选进行比较、消歧与质量判断",
                "when_to_use": "候选存在多个可行项，需要进一步判优时",
                "when_not_to_use": "尚无候选可比较时",
            },
            {
                "name": "patch",
                "purpose": "将结构化增量修改应用到 EditDraft",
                "when_to_use": "已形成明确编辑决策并需落盘到草案时",
                "when_not_to_use": "需求仍含关键不确定性、应先澄清或检索时",
            },
            {
                "name": "preview",
                "purpose": "生成可审阅预览以验证当前草案效果",
                "when_to_use": "需要向用户展示阶段性结果或验证可视化效果时",
                "when_not_to_use": "草案尚未形成可评估结构时",
            },
        ],
        "source": "tool_layer_minimal_contract",
    }


def build_working_memory_state(
    *,
    chat_history_summary: list[str],
    tool_observations: list[dict[str, Any]],
) -> dict[str, Any]:
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

    return {
        "recent_chat_summary": chat_history_summary[-6:],
        "recent_decisions": recent_decisions,
        "recent_tool_observations": recent_observation_summary,
        "pending_risks": pending_risks,
        "open_questions": [],
    }


def build_runtime_capabilities_state() -> dict[str, Any]:
    return {
        "planner_loop": "implemented",
        "tool_execution": "todo",
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
        scope=build_scope_state(target=target, draft_summary=draft_summary),
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
        "goal": {
            "goal_summary": runtime_state.goal["goal_summary"],
            "success_criteria": runtime_state.goal["success_criteria"],
            "open_questions": runtime_state.goal["open_questions"],
        },
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
        "[Identity]\n"
        "You are EntroCut Core Planner, responsible for the next best editing decision.\n"
        "[Tool Usage Policy]\n"
        "Use tools only when needed. Prefer read before risky operations."
        " For scope expansion, retrieve first; for candidate judgment, inspect;"
        " for deterministic draft updates, patch; for review output, preview.\n"
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
