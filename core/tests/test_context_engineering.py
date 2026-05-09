from __future__ import annotations

import sys
import unittest
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1]
if str(CORE_DIR) not in sys.path:
    sys.path.append(str(CORE_DIR))

from application.context import (
    build_goal_state,
    build_planner_context_packet,
    build_planner_system_prompt,
    build_scope_state,
    build_tool_capability_state,
    build_working_memory_state,
)


class ContextEngineeringTest(unittest.TestCase):
    def test_goal_state_extracts_structured_fields(self) -> None:
        goal = build_goal_state(
            prompt="  做一个旅行视频开头，强调轻快节奏和清晨氛围  ",
            runtime_goal_state={"brief": "旅行片头", "constraints": ["15 秒"], "preferences": ["轻快"]},
        )
        self.assertEqual(goal["user_intent"], "做一个旅行视频开头，强调轻快节奏和清晨氛围")
        self.assertEqual(goal["goal_summary"], "旅行片头")
        self.assertIn("15 秒", goal["constraints"])
        self.assertIn("轻快", goal["preferences"])
        self.assertTrue(any("节奏" in item for item in goal["success_criteria"]))
        self.assertIn("open_questions", goal)

    def test_scope_state_prefers_target_then_draft_selection(self) -> None:
        shot_scope = build_scope_state(
            target={"shot_id": "shot_1"},
            draft_summary={"selected_scene_id": "scene_1"},
            focus_state={"scope_type": "scene", "scene_id": "scene_runtime"},
        )
        self.assertEqual(shot_scope["scope_type"], "shot")
        self.assertEqual(shot_scope["selected_shot_id"], "shot_1")

        scene_scope = build_scope_state(
            target=None,
            draft_summary={"selected_scene_id": "scene_2"},
            focus_state={"scope_type": "scene", "scene_id": "scene_runtime"},
        )
        self.assertEqual(scene_scope["scope_type"], "scene")
        self.assertEqual(scene_scope["selected_scene_id"], "scene_runtime")

        project_scope = build_scope_state(target=None, draft_summary={}, focus_state={"scope_type": "project"})
        self.assertEqual(project_scope["scope_type"], "project")

    def test_tools_injection_contains_read_contract(self) -> None:
        tools = build_tool_capability_state(
            capabilities={
                "chat_mode": "planning_only",
                "can_retrieve": False,
                "can_inspect": False,
                "can_patch_draft": False,
                "can_preview": False,
                "blocking_reasons": ["media_index_not_ready"],
            },
            media_summary={"asset_count": 1, "indexed_clip_count": 0, "retrieval_ready": False},
        )
        self.assertIn("read", tools["enabled"])
        self.assertIn("retrieve", tools["disabled"])
        self.assertEqual(tools["disabled"]["retrieve"], "media_index_not_ready")
        self.assertEqual(tools["chat_mode"], "planning_only")

    def test_planner_prompt_allows_inspect_without_retrieval_for_known_clip(self) -> None:
        prompt = build_planner_system_prompt()
        self.assertIn("Use retrieve to find candidate clips", prompt)
        self.assertIn("Use inspect only to ask a visual model to describe one known clip", prompt)
        self.assertIn("Do comparison, ranking, choice, and editing decisions yourself", prompt)
        self.assertIn("current_user_request.text is the highest-priority instruction", prompt)
        self.assertIn("interface InspectInput", prompt)
        self.assertNotIn("compare", prompt)
        self.assertIn("Never return stringified JSON", prompt)

    def test_working_memory_is_structured(self) -> None:
        memory = build_working_memory_state(
            chat_history_summary=["user: 我要一个片头", "assistant: 先做占位草案"],
            tool_observations=[
                {"tool_name": "retrieve", "success": True, "summary": "召回了8个候选"},
                {"tool_name": "inspect", "success": False, "summary": "候选区分度不足"},
            ],
            runtime_state={
                "conversation_state": {"pending_questions": ["目标时长?"], "confirmed_facts": ["做片头"]},
                "retrieval_state": {"blocking_reason": "media_index_not_ready"},
            },
        )
        self.assertIn("recent_chat_summary", memory)
        self.assertIn("recent_decisions", memory)
        self.assertIn("recent_tool_observations", memory)
        self.assertIn("pending_risks", memory)
        self.assertIn("open_questions", memory)
        self.assertEqual(len(memory["recent_tool_observations"]), 2)
        self.assertIn("目标时长?", memory["open_questions"])
        self.assertIn("做片头", memory["confirmed_facts"])

    def test_planner_input_is_pruned_from_runtime_state(self) -> None:
        packet = build_planner_context_packet(
            project_id="proj_1",
            iteration=1,
            prompt="做一个旅行开头",
            target=None,
            project={"id": "proj_1", "title": "T", "lifecycle_state": "active"},
            summary_state="editing",
            runtime_state={
                "goal_state": {"brief": "旅行开头", "constraints": ["15 秒"], "preferences": [], "open_questions": []},
                "focus_state": {"scope_type": "scene", "scene_id": "scene_runtime", "shot_id": None},
                "conversation_state": {"pending_questions": ["节奏?"], "confirmed_facts": ["旅行"], "latest_user_feedback": "unknown"},
                "retrieval_state": {"last_query": "departure", "candidate_clip_ids": ["clip_1"], "retrieval_ready": True, "blocking_reason": None},
                "execution_state": {"agent_run_state": "planning", "current_task_id": "task_1", "last_tool_name": "read", "last_error": None},
            },
            media_summary={"asset_count": 2, "ready_asset_count": 2, "indexed_clip_count": 4, "retrieval_ready": True},
            capabilities={
                "chat_mode": "editing",
                "can_send_chat": True,
                "can_retrieve": True,
                "can_inspect": True,
                "can_patch_draft": True,
                "can_preview": False,
                "can_export": False,
                "blocking_reasons": [],
            },
            draft_summary={
                "draft_id": "d1",
                "draft_version": 1,
                "asset_count": 1,
                "clip_count": 1,
                "shot_count": 0,
                "scene_count": 0,
                "selected_scene_id": None,
                "selected_shot_id": None,
                "clip_excerpt": [
                    {
                        "clip_id": "clip_1",
                        "asset_id": "asset_1",
                        "visual_desc": "候选片段 1",
                        "semantic_tags": [],
                    }
                ],
            },
            chat_history_summary=[],
            tool_observations=[],
        )
        self.assertIn("user_intent", packet.runtime_state.goal)
        self.assertEqual(packet.planner_input["current_user_request"]["text"], "做一个旅行开头")
        self.assertEqual(packet.planner_input["current_user_request"]["priority"], "must_answer_first")
        self.assertNotIn("user_intent", packet.planner_input["goal"])
        self.assertIn("goal_summary", packet.planner_input["goal"])
        self.assertEqual(packet.planner_input["project"]["summary_state"], "editing")
        self.assertEqual(packet.planner_input["capabilities"]["chat_mode"], "editing")
        self.assertTrue(packet.planner_input["media"]["retrieval_ready"])
        self.assertNotIn("runtime_state", packet.planner_input)
        self.assertEqual(packet.planner_input["draft"]["clips"][0]["alias"], "clip1")


if __name__ == "__main__":
    unittest.main()
