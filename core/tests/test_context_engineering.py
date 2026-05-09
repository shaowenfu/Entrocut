from __future__ import annotations

import sys
import unittest
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[1]
if str(CORE_DIR) not in sys.path:
    sys.path.append(str(CORE_DIR))

from application.context import build_agent_prompt
from contracts import AssetModel, ClipModel, EditDraftModel, SceneModel, ShotModel
from runtime.helpers import _now_iso


class AgentPromptAssemblyTest(unittest.TestCase):
    def _draft(self) -> EditDraftModel:
        now = _now_iso()
        return EditDraftModel(
            id="draft_1",
            project_id="proj_1",
            version=2,
            status="ready",
            assets=[
                AssetModel(
                    id="asset_1",
                    name="travel.mp4",
                    duration_ms=10000,
                    type="video",
                    source_path="/tmp/travel.mp4",
                    lifecycle_state="active",
                    processing_stage="ready",
                )
            ],
            clips=[
                ClipModel(
                    id="clip_1",
                    asset_id="asset_1",
                    source_start_ms=0,
                    source_end_ms=5000,
                    visual_desc="wide ocean shot",
                    visual_description="blue ocean with open horizon",
                    semantic_tags=["ocean", "wide"],
                )
            ],
            shots=[
                ShotModel(
                    id="shot_1",
                    clip_id="clip_1",
                    source_in_ms=0,
                    source_out_ms=4000,
                    order=0,
                    enabled=True,
                    label="Opening",
                    intent="establish travel mood",
                )
            ],
            scenes=[
                SceneModel(
                    id="scene_1",
                    shot_ids=["shot_1"],
                    order=0,
                    enabled=True,
                    label="Opening",
                    intent="open the story",
                )
            ],
            selected_scene_id="scene_1",
            selected_shot_id="shot_1",
            created_at=now,
            updated_at=now,
        )

    def test_prompt_contains_five_sections_and_tool_guidance(self) -> None:
        prompt = build_agent_prompt(
            user_prompt="把开头换成大海镜头",
            edit_draft=self._draft(),
            chat_turns=[],
            tool_observations=[],
            selected_scene_id="scene_1",
            selected_shot_id="shot_1",
        )

        self.assertIn("=== 1. System Context & Global State", prompt)
        self.assertIn("=== 2. Chat History", prompt)
        self.assertIn("=== 3. Current Loop Observations", prompt)
        self.assertIn("=== 4. Available Tools", prompt)
        self.assertIn("=== 5. Strict JSON Output", prompt)
        self.assertIn("什么时候调用", prompt)
        self.assertIn("inspection_goal", prompt)
        self.assertIn("insert_shot", prompt)
        self.assertNotIn("Workspace Capability", prompt)
        self.assertNotIn("Tool Availability", prompt)

    def test_global_toc_does_not_leak_clip_visual_details(self) -> None:
        prompt = build_agent_prompt(
            user_prompt="看看开场",
            edit_draft=self._draft(),
            chat_turns=[],
            tool_observations=[],
            selected_scene_id="scene_1",
            selected_shot_id="shot_1",
        )

        first_section = prompt.split("=== 2. Chat History", maxsplit=1)[0]
        self.assertIn("scene_1", first_section)
        self.assertIn("shot_1", first_section)
        self.assertNotIn("blue ocean with open horizon", first_section)
        self.assertNotIn("wide ocean shot", first_section)


if __name__ == "__main__":
    unittest.main()
