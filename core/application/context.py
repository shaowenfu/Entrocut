from __future__ import annotations

import json
from typing import Any

from contracts import ChatTurnModel, EditDraftModel, ToolObservationModel


def _text(value: Any) -> str:
    normalized = " ".join(str(value or "").strip().split())
    return normalized or "none"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _shot_duration_ms(source_in_ms: int, source_out_ms: int) -> int:
    return max(0, int(source_out_ms) - int(source_in_ms))


def _format_duration_ms(ms: int) -> str:
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{ms}ms ({minutes}:{seconds:02d})"


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def _shots_by_id(draft: EditDraftModel) -> dict[str, Any]:
    return {shot.id: shot for shot in draft.shots}


def _scene_rows(draft: EditDraftModel) -> list[str]:
    scenes = sorted(draft.scenes or [], key=lambda item: item.order)
    if not scenes:
        return ["- scene_id: none\n  order: 0\n  enabled: false\n  label: none\n  intent: none\n  shot_ids: []"]
    rows: list[str] = []
    for scene in scenes:
        rows.append(
            "\n".join(
                [
                    f"- scene_id: {scene.id}",
                    f"  order: {scene.order}",
                    f"  enabled: {str(scene.enabled).lower()}",
                    f"  label: {_text(scene.label)}",
                    f"  intent: {_text(scene.intent)}",
                    f"  shot_ids: {_json(scene.shot_ids)}",
                ]
            )
        )
    return rows


def _storyline_rows(draft: EditDraftModel) -> list[str]:
    scenes = sorted(draft.scenes or [], key=lambda item: item.order)
    shots_by_id = _shots_by_id(draft)
    if not scenes:
        return ["- scene_id: none\n  narrative_position: 0\n  intent: none\n  shots: []"]
    rows: list[str] = []
    for scene in scenes:
        shot_lines = []
        for shot_id in scene.shot_ids:
            shot = shots_by_id.get(shot_id)
            if shot is None:
                continue
            shot_lines.append(f"    - shot_id: {shot.id}\n      intent: {_text(shot.intent)}")
        rows.append(
            "\n".join(
                [
                    f"- scene_id: {scene.id}",
                    f"  narrative_position: {scene.order}",
                    f"  intent: {_text(scene.intent)}",
                    "  shots:",
                    "\n".join(shot_lines) if shot_lines else "    []",
                ]
            )
        )
    return rows


def render_asset_clip_inventory(edit_draft: EditDraftModel) -> str:
    lines = ["=== 2. Asset & Clip Inventory（素材与片段清单） ===", ""]

    # --- 1. Asset Summary ---
    lines.append("Asset Summary（素材摘要）:")
    active_assets = [a for a in edit_draft.assets if a.lifecycle_state == "active"]
    if not active_assets:
        lines.append("  (no assets)")
    else:
        for asset in active_assets:
            lines.append(
                f"  - asset_id: {asset.id} | name: {asset.name} | type: {asset.type} | "
                f"duration: {_format_duration_ms(asset.duration_ms)} | "
                f"clips: {asset.indexed_clip_count}/{asset.clip_count} | "
                f"stage: {asset.processing_stage}"
            )
    lines.append("")

    # --- 2. Timeline Shot-to-Clip Mapping ---
    clips_by_id = {c.id: c for c in edit_draft.clips}
    shots_by_id = {s.id: s for s in edit_draft.shots}

    lines.append("Timeline Shot-to-Clip Mapping（时间线镜头-片段映射）:")
    if not edit_draft.scenes:
        lines.append("  (no timeline)")
    else:
        scenes = sorted(edit_draft.scenes, key=lambda s: s.order)
        for scene in scenes:
            lines.append(f"  Scene: {scene.id} (order: {scene.order}) \"{_text(scene.label)}\"")
            if not scene.shot_ids:
                lines.append("    (no shots)")
            else:
                for shot_id in scene.shot_ids:
                    shot = shots_by_id.get(shot_id)
                    if shot is None:
                        lines.append(f"    - shot_id: {shot_id} | (shot not found)")
                        continue
                    clip_exists = shot.clip_id in clips_by_id
                    clip_id_display = shot.clip_id if clip_exists else f"{shot.clip_id} (not found in active clips)"
                    shot_duration = _shot_duration_ms(shot.source_in_ms, shot.source_out_ms)
                    lines.append(
                        f"    - shot_id: {shot.id} | clip_id: {clip_id_display} | "
                        f"source: {shot.source_in_ms}-{shot.source_out_ms}ms ({shot_duration // 1000}s) | "
                        f"intent: {_text(shot.intent)}"
                    )
    lines.append("")

    # --- 3. Unused Clip Pool ---
    # Collect clip_ids that are referenced by shots AND exist in the clip list
    referenced_clip_ids: set[str] = set()
    for shot in edit_draft.shots:
        if shot.clip_id in clips_by_id:
            referenced_clip_ids.add(shot.clip_id)

    unused_clips = [c for c in edit_draft.clips if c.id not in referenced_clip_ids]

    lines.append("Unused Clip Pool（未使用片段池）:")
    if not unused_clips:
        lines.append("  (all clips are referenced by timeline shots)")
    else:
        # Group unused clips by asset
        unused_by_asset: dict[str, list] = {}
        for clip in unused_clips:
            unused_by_asset.setdefault(clip.asset_id, []).append(clip)

        active_assets_by_id = {a.id: a for a in active_assets}
        for asset_id, clips_list in unused_by_asset.items():
            asset = active_assets_by_id.get(asset_id)
            asset_name = asset.name if asset else asset_id
            lines.append(f"  Asset: {asset_id} \"{asset_name}\" ({len(clips_list)} clips)")
            for clip in clips_list:
                clip_duration = max(0, clip.source_end_ms - clip.source_start_ms)
                tags = clip.semantic_tags[:4]
                tags_str = json.dumps(tags, ensure_ascii=False)
                desc = clip.visual_description or clip.visual_desc
                visual = _truncate(desc, 80)
                lines.append(
                    f"    - clip_id: {clip.id} | "
                    f"source: {clip.source_start_ms}-{clip.source_end_ms}ms ({clip_duration // 1000}s) | "
                    f"tags: {tags_str} | "
                    f"visual: {visual}"
                )

    return "\n".join(lines)


def _assistant_tools(turn: dict[str, Any]) -> str:
    tools: list[str] = []
    for step in turn.get("agent_steps") or []:
        if not isinstance(step, dict):
            continue
        details = step.get("details") if isinstance(step.get("details"), dict) else {}
        tool_name = details.get("tool_name")
        if isinstance(tool_name, str) and tool_name and tool_name not in tools:
            tools.append(tool_name)
    return f"[tool: {', '.join(tools)}] " if tools else ""


def _turn_to_dict(turn: ChatTurnModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(turn, dict):
        return turn
    return turn.model_dump()


def render_static_agent_prompt() -> str:
    return """你是 EntroCut Editing Agent（剪辑智能体）。

你的任务是把用户的自然语言剪辑意图转成结构化剪辑动作。你只修改 EditDraft（剪辑草稿），不直接处理底层媒体文件，不伪造渲染结果，不伪造视觉观察结果。

核心术语：
- Asset（资产）：原始媒体文件。
- Clip（片段）：Asset（资产）经过切分和索引得到的候选媒体片段。
- Shot（镜头）：Timeline（时间线）上的最小剪辑单元，引用一个 Clip（片段）并声明实际使用的源时间范围。
- Scene（场景）：多个 Shot（镜头）的叙事组合。
- Storyline（故事线）：Scene（场景）之间的叙事顺序与意图骨架。
- EditDraft（剪辑草稿）：当前项目的结构化剪辑配方。

决策原则：
1. 当前用户请求优先于历史对话。
2. Global TOC（全局目录）只提供结构骨架；涉及画面、时间切口、标签、素材细节时，必须调用 read。
3. 需要找新素材时调用 retrieve。
4. 需要确认一个已知 Clip（片段）的画面内容时调用 inspect。
5. 已有明确剪辑决策时调用 patch。
6. 需要让用户检查效果时调用 preview。
7. 不要猜测 Tool（工具）结果。
8. 不要输出 Markdown（标记语言）。
9. 不要输出解释性推理过程。
10. 每轮只能请求一个 Tool（工具）或给出一个 final（最终）回复。
11. 当你遇到需要用户品味判断、意图澄清或方向选择时，使用 ask_user 状态。向用户提出一个明确的用中文书写的问题，并给出 2-4 个具体选项。
12. 不要对同一个 Clip（片段）重复调用 inspect 或 read。若工具观察结果中已包含所需信息，直接基于已有信息做出 final 回复或调用其他工具。"""


def render_system_context_and_global_state(
    *,
    user_prompt: str,
    edit_draft: EditDraftModel,
    selected_scene_id: str,
    selected_shot_id: str,
) -> str:
    return "\n".join(
        [
            "=== 1. System Context & Global State（系统设定与全局状态） ===",
            "",
            "Current User Request（当前用户请求）:",
            _text(user_prompt),
            "",
            "Current Focus（当前焦点）:",
            f"- selected_scene_id: {_text(selected_scene_id)}",
            f"- selected_shot_id: {_text(selected_shot_id)}",
            "",
            "Global TOC（全局目录）:",
            f"- draft_id: {edit_draft.id}",
            f"- draft_version: {edit_draft.version}",
            f"- scene_count: {len(edit_draft.scenes or [])}",
            f"- shot_count: {len(edit_draft.shots)}",
            "- scenes:",
            "\n".join(_scene_rows(edit_draft)),
            "",
            "Storyline Digest（故事线摘要）:",
            "\n".join(_storyline_rows(edit_draft)),
        ]
    )


def render_chat_history(chat_turns: list[ChatTurnModel | dict[str, Any]]) -> str:
    recent_turns = [_turn_to_dict(turn) for turn in chat_turns[-10:]]
    lines = ["=== 3. Chat History（对话历史） ===", ""]
    if not recent_turns:
        lines.append("暂无。")
        return "\n".join(lines)
    for turn in recent_turns:
        if turn.get("role") == "user":
            turn_type = turn.get("type")
            if turn_type == "answer":
                selected = turn.get("selected_option_id") or "custom"
                answer_text = turn.get("custom_answer") or selected
                lines.append(f"User: [answer to question {_text(turn.get('question_id'))}] {_text(answer_text)}")
            else:
                lines.append(f"User: {_text(turn.get('content'))}")
        elif turn.get("role") == "assistant":
            turn_type = turn.get("type")
            if turn_type == "question":
                options_text = ", ".join(
                    f"{opt.get('label', '')}" for opt in (turn.get("options") or []) if isinstance(opt, dict)
                )
                lines.append(
                    f"Assistant: [question {_text(turn.get('question_id') or turn.get('id'))}] {_text(turn.get('question'))}"
                )
                if options_text:
                    lines.append(f"  Options: {options_text}")
            else:
                lines.append(f"Assistant: {_assistant_tools(turn)}{_text(turn.get('assistant_reply'))}")
    return "\n".join(lines)


def render_current_loop_observations(tool_observations: list[ToolObservationModel | dict[str, Any]]) -> str:
    lines = ["=== 4. Current Loop Observations（当前循环观测） ===", ""]
    if not tool_observations:
        lines.append("暂无。")
        return "\n".join(lines)
    for index, observation in enumerate(tool_observations, start=1):
        payload = observation if isinstance(observation, dict) else observation.model_dump()
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        lines.extend(
            [
                f"[Step {index}]",
                f"- tool_name: {_text(payload.get('tool_name'))}",
                f"- success: {str(bool(payload.get('success'))).lower()}",
                f"- summary: {_text(payload.get('summary'))}",
                f"- output: {_json(output)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def render_available_tools() -> str:
    return """=== 5. Available Tools（可用工具） ===

1. read
作用：读取当前剪辑业务事实和系统信息。它是 Agent 的显微镜，用于从骨架上下文进入局部细节。
什么时候调用：需要知道 Storyline（故事线）、Scene（场景）里的 Shot（镜头）、Shot（镜头）的时间切口、Clip（片段）的画面描述或标签时。
什么时候不要调用：当前 Prompt（提示词）骨架已经足够做最终回复，或只是需要找新素材时。
Input:
{
  "target_type": "draft_tree" | "storyline" | "scene" | "shot" | "clip",
  "target_id": "string"
}
target_id 规则：draft_tree/storyline 传 "root"；scene/shot/clip 传真实 ID。

2. retrieve
作用：基于多模态向量检索技术，通过文本 Query（查询）在素材池中召回候选 Clip（片段）。它只负责高召回初筛，不负责判断哪个最好。
什么时候调用：用户要替换、补充或寻找某类画面，而当前已知 Clip（片段）不足以决策时。
什么时候不要调用：已经有明确 clip_id 需要观察时；需要最终选择、排序或剪辑时。
Input:
{
  "query": "string"
}

3. inspect
作用：调用 VLM（多模态大模型）观察一个已知 Clip（片段）的画面。它是 Agent 的眼睛。
什么时候调用：已有明确 clip_id，但需要确认主体、动作、场景、景别、稳定性、情绪或剪辑价值时。
什么时候不要调用：还没有候选 Clip（片段）时；需要执行剪辑修改时；需要比较大量候选时。
Input:
{
  "clip_id": "string",
  "inspection_goal": "string" //给VLM的提示词，详细描述需要观察的内容和关注点，可以是一个或多个具体问题。
}

4. patch
作用：把明确的剪辑决策写入 EditDraft（剪辑草稿）。
什么时候调用：已经知道要插入、替换或删除哪个 Shot（镜头），且拥有真实 scene_id/shot_id/clip_id 和时间切口时。
什么时候不要调用：还不知道目标 Shot（镜头）、Clip（片段）或时间切口时；还需要视觉确认时。
Input:
{
  "operations": [
    {
      "op": "insert_shot",
      "scene_id": "string",
      "index": number,
      "clip_id": "string",
      "source_in_ms": number,
      "source_out_ms": number,
      "intent": "string"
    }
  ]
}
也可以使用 replace_shot 或 delete_shot：
replace_shot 需要 op、shot_id、clip_id、source_in_ms、source_out_ms、intent。
delete_shot 需要 op、shot_id、deletion_reason。

5. preview
作用：根据当前 EditDraft（剪辑草稿）生成真实预览文件。
什么时候调用：草稿已经被修改，用户需要检查结果时。
什么时候不要调用：草稿还没有可渲染结构时；只是需要继续读取、检索或修改时。
Input:
{
  "reason": "string"
}"""


def render_strict_json_output_contract() -> str:
    return """=== 6. Strict JSON Output（严格 JSON 输出） ===

必须只输出一个合法 JSON 对象，不要输出 Markdown、代码围栏、解释文本或字符串化 JSON。

interface PlannerDecision {
  status: "requires_tool" | "final" | "ask_user";
  tool_name: "read" | "retrieve" | "inspect" | "patch" | "preview" | null;
  tool_input: object | null;
  assistant_reply: string | null;
  question: {
    question: string;
    options: [{id: string; label: string; description: string | null}];
    allow_custom: boolean;
    context_brief: string | null;
  } | null;
  current_focus: {
    target_type: "project" | "scene" | "shot" | "clip";
    target_id: string;
  };
}

规则：
- status 是 "requires_tool" 时，tool_name 必须是一个工具名，tool_input 必须是对应工具输入，assistant_reply 必须是 null，question 必须是 null。
- status 是 "final" 时，tool_name 必须是 null，tool_input 必须是 null，question 必须是 null，assistant_reply 必须是中文用户回复。
- status 是 "ask_user" 时，tool_name 必须是 null，tool_input 必须是 null，assistant_reply 必须是 null，question 必须包含：
    question: 用中文提出的明确问题
    options: 2-4 个选项，每个包含 id/label/description
    allow_custom: 是否允许用户自定义回答
    context_brief: 简短说明当前上下文和目标
- current_focus 始终必填。无具体对象时使用 {"target_type":"project","target_id":"project"}。
- 每轮只能请求一个工具或提出一个问题。"""


def build_agent_prompt(
    *,
    user_prompt: str,
    edit_draft: EditDraftModel,
    chat_turns: list[ChatTurnModel | dict[str, Any]],
    tool_observations: list[ToolObservationModel | dict[str, Any]],
    selected_scene_id: str,
    selected_shot_id: str,
) -> str:
    sections = [
        render_static_agent_prompt(),
        render_system_context_and_global_state(
            user_prompt=user_prompt,
            edit_draft=edit_draft,
            selected_scene_id=selected_scene_id,
            selected_shot_id=selected_shot_id,
        ),
        render_asset_clip_inventory(edit_draft),
        render_chat_history(chat_turns),
        render_current_loop_observations(tool_observations),
        render_available_tools(),
        render_strict_json_output_contract(),
    ]
    return "\n\n".join(sections)
