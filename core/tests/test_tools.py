import os
import tempfile
import time
import unittest
from pathlib import Path

from app.tools.export_renderer import ExportRendererTool
from app.tools.ingest_coordinator import IngestCoordinatorTool
from app.tools.media_scanner import MediaScannerTool
from app.tools.path_normalizer import PathNormalizerTool
from app.tools.preview_renderer import PreviewRendererTool


class CoreToolTests(unittest.TestCase):
    def test_path_normalizer_resolves_symlink_to_same_hash(self) -> None:
        normalizer = PathNormalizerTool()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "clip.mp4"
            target.write_bytes(b"video")
            link = root / "clip_link.mp4"
            try:
                os.symlink(target, link)
            except (AttributeError, NotImplementedError, OSError):
                self.skipTest("symlink_not_supported")

            target_result = normalizer.run(str(target))
            link_result = normalizer.run(str(link))

            self.assertTrue(target_result.ok)
            self.assertTrue(link_result.ok)
            self.assertEqual(target_result.payload["source_hash"], link_result.payload["source_hash"])

    def test_media_scanner_filters_and_deduplicates(self) -> None:
        normalizer = PathNormalizerTool()
        scanner = MediaScannerTool(normalizer)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "clip.mp4"
            note = root / "note.txt"
            video.write_bytes(b"video")
            note.write_text("ignore", encoding="utf-8")

            existing_hash = normalizer.run(str(video)).payload["source_hash"]
            result = scanner.run(str(root), existing_hashes={existing_hash})

            self.assertTrue(result.ok)
            self.assertEqual(result.payload["total_found"], 1)
            self.assertEqual(result.payload["skipped_count"], 1)
            self.assertEqual(result.payload["filtered_count"], 1)
            self.assertEqual(result.payload["new_assets"], [])

    def test_ingest_coordinator_tracks_phase_progress(self) -> None:
        coordinator = IngestCoordinatorTool()

        started = coordinator.run("start_phase", phase="scan", total_items=4)
        updated = coordinator.run("update_progress", phase="scan", items_processed=2)
        completed = coordinator.run("complete_phase", phase="scan")

        self.assertTrue(started.ok)
        self.assertTrue(updated.ok)
        self.assertTrue(completed.ok)
        self.assertEqual(updated.payload["current_phase"], "scan")
        self.assertAlmostEqual(updated.payload["overall_progress"], 0.025, places=3)
        self.assertEqual(completed.payload["phase_stats"]["scan"]["status"], "completed")

    def test_preview_renderer_is_idempotent(self) -> None:
        renderer = PreviewRendererTool()
        timeline = {"project_id": "proj_preview", "duration_ms": 12_000}

        first = renderer.run(timeline, quality="low", output_format="webm", project_id="proj_preview")
        second = renderer.run(timeline, quality="low", output_format="webm", project_id="proj_preview")

        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertEqual(first.payload["preview_url"], second.payload["preview_url"])
        self.assertEqual(first.payload["render_type"], "preview")

    def test_export_renderer_generates_unique_outputs(self) -> None:
        renderer = ExportRendererTool()
        timeline = {"project_id": "proj_export", "duration_ms": 30_000}

        first = renderer.run(timeline, format="mp4", project_id="proj_export")
        time.sleep(0.001)
        second = renderer.run(timeline, format="mp4", project_id="proj_export")

        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertNotEqual(first.payload["timestamp"], second.payload["timestamp"])
        self.assertNotEqual(first.payload["output_path"], second.payload["output_path"])
        self.assertEqual(first.payload["render_type"], "export")


if __name__ == "__main__":
    unittest.main()
