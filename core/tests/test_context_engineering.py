from __future__ import annotations

import unittest

from core.context import (
    build_goal_state,
    build_planner_context_packet,
    build_scope_state,
    build_tool_capability_state,
    build_working_memory_state,
)


class ContextEngineeringTest(unittest.TestCase):
    def test_goal_state_extracts_structured_fields(self) -> None:
        goal = build_goal_state(prompt="  做一个旅行视频开头，强调轻快节奏和清晨氛围  ")
        self.assertEqual(goal["user_intent"], "做一个旅行视频开头，强调轻快节奏和清晨氛围")
        self.assertEqual(goal["goal_summary"], "做一个旅行视频开头，强调轻快节奏和清晨氛围")
        self.assertTrue(any("节奏" in item for item in goal["success_criteria"]))
        self.assertIn("open_questions", goal)

    def test_scope_state_prefers_target_then_draft_selection(self) -> None:
        shot_scope = build_scope_state(target={"shot_id": "shot_1"}, draft_summary={"selected_scene_id": "scene_1"})
        self.assertEqual(shot_scope["scope_type"], "shot")
        self.assertEqual(shot_scope["selected_shot_id"], "shot_1")

        scene_scope = build_scope_state(target=None, draft_summary={"selected_scene_id": "scene_2"})
        self.assertEqual(scene_scope["scope_type"], "scene")
        self.assertEqual(scene_scope["selected_scene_id"], "scene_2")

        project_scope = build_scope_state(target=None, draft_summary={})
        self.assertEqual(project_scope["scope_type"], "project")

    def test_tools_injection_contains_read_contract(self) -> None:
        tools = build_tool_capability_state()
        tool_names = [item["name"] for item in tools["available_tools"]]
        self.assertIn("read", tool_names)
        read_tool = next(item for item in tools["available_tools"] if item["name"] == "read")
        self.assertIn("when_to_use", read_tool)
        self.assertIn("when_not_to_use", read_tool)

    def test_working_memory_is_structured(self) -> None:
        memory = build_working_memory_state(
            chat_history_summary=["user: 我要一个片头", "assistant: 先做占位草案"],
            tool_observations=[
                {"tool_name": "retrieve", "success": True, "summary": "召回了8个候选"},
                {"tool_name": "inspect", "success": False, "summary": "候选区分度不足"},
            ],
        )
        self.assertIn("recent_chat_summary", memory)
        self.assertIn("recent_decisions", memory)
        self.assertIn("recent_tool_observations", memory)
        self.assertIn("pending_risks", memory)
        self.assertIn("open_questions", memory)
        self.assertEqual(len(memory["recent_tool_observations"]), 2)

    def test_planner_input_is_pruned_from_runtime_state(self) -> None:
        packet = build_planner_context_packet(
            project_id="proj_1",
            iteration=1,
            prompt="做一个旅行开头",
            target=None,
            project={"title": "T", "workflow_state": "media_ready"},
            draft_summary={
                "draft_id": "d1",
                "draft_version": 1,
                "asset_count": 1,
                "clip_count": 1,
                "shot_count": 0,
                "scene_count": 0,
                "selected_scene_id": None,
                "selected_shot_id": None,
                "clip_excerpt": [],
            },
            chat_history_summary=[],
            tool_observations=[],
        )
        self.assertIn("user_intent", packet.runtime_state.goal)
        self.assertNotIn("user_intent", packet.planner_input["goal"])
        self.assertIn("goal_summary", packet.planner_input["goal"])


if __name__ == "__main__":
    unittest.main()
