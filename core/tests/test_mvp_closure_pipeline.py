from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from core.helpers import _entity_id, _now_iso
from core.patching import apply_edit_draft_patch
from core.rendering import build_render_plan
from core.schemas import AssetModel, ClipModel, EditDraftModel, EditDraftPatchModel, ShotModel

sys.modules.setdefault(
    "ingestion",
    SimpleNamespace(
        detect_scenes=lambda *args, **kwargs: [],
        extract_and_stitch_frames=lambda *args, **kwargs: "",
    ),
)

from core.store import InMemoryProjectStore, TaskModel


class MvpClosurePipelineTest(unittest.TestCase):
    def _make_draft(self) -> EditDraftModel:
        now = _now_iso()
        asset = AssetModel(
            id="asset_1",
            name="sample.mp4",
            duration_ms=12000,
            type="video",
            source_path="/tmp/not_found_source.mp4",
            processing_stage="ready",
            processing_progress=100,
            clip_count=1,
            indexed_clip_count=1,
            updated_at=now,
        )
        clip = ClipModel(
            id="clip_1",
            asset_id="asset_1",
            source_start_ms=0,
            source_end_ms=6000,
            visual_desc="city sunrise",
            semantic_tags=["city", "sunrise"],
        )
        shot = ShotModel(
            id="shot_1",
            clip_id="clip_1",
            source_in_ms=500,
            source_out_ms=3500,
            order=0,
            enabled=True,
        )
        return EditDraftModel(
            id=_entity_id("draft"),
            project_id="proj_1",
            version=1,
            status="ready",
            assets=[asset],
            clips=[clip],
            shots=[shot],
            scenes=None,
            selected_scene_id=None,
            selected_shot_id=shot.id,
            created_at=now,
            updated_at=now,
        )

    def test_build_render_plan_from_shots(self) -> None:
        draft = self._make_draft()
        plan = build_render_plan(draft)
        self.assertEqual(plan.project_id, draft.project_id)
        self.assertEqual(len(plan.segments), 1)
        self.assertEqual(plan.segments[0].source_in_ms, 500)
        self.assertEqual(plan.estimated_duration_ms, 3000)

    def test_apply_patch_insert_and_reorder(self) -> None:
        draft = self._make_draft().model_copy(update={"shots": []})
        patch = EditDraftPatchModel(
            operations=[
                {"op": "insert_shot", "clip_id": "clip_1", "index": 0},
                {"op": "insert_shot", "clip_id": "clip_1", "index": 1},
            ],
            reasoning_summary="assemble first cut",
        )
        next_draft = apply_edit_draft_patch(draft, patch)
        self.assertEqual(len(next_draft.shots), 2)
        self.assertEqual(next_draft.shots[0].order, 0)
        self.assertEqual(next_draft.shots[1].order, 1)

    def test_export_task_uses_renderer_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = InMemoryProjectStore(app_data_root=tmpdir)
            created = asyncio.run(store.create_project(type("P", (), {"title": "T", "prompt": None, "media": None})()))
            project_id = str(created["project"]["id"])
            draft = self._make_draft().model_copy(update={"project_id": project_id})
            record = store.get_project_or_raise(project_id)
            record["edit_draft"] = draft.model_dump()

            fake_output = Path(tmpdir) / "projects" / project_id / "exports" / f"{project_id}_draft.mp4"
            fake_output.parent.mkdir(parents=True, exist_ok=True)
            fake_output.write_bytes(b"00")

            with patch("core.store.render_export", return_value={
                "output_url": fake_output.resolve().as_uri(),
                "duration_ms": 3000,
                "file_size_bytes": 2,
            }):
                now = _now_iso()
                task = TaskModel(
                    id=_entity_id("task_render"),
                    slot="export",
                    type="render",
                    status="queued",
                    owner_type="draft",
                    owner_id=draft.id,
                    progress=0,
                    message="Export queued",
                    created_at=now,
                    updated_at=now,
                )
                asyncio.run(store._run_export(project_id, type("E", (), {"format": "mp4", "quality": "preview"})(), task))

            updated = store.get_project_or_raise(project_id)
            self.assertIsNotNone(updated.get("export_result"))
            self.assertIn("output_url", updated["export_result"])


if __name__ == "__main__":
    unittest.main()
