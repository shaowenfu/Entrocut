from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from process.video_renderer import RenderError, VideoRenderer
from tests.utils import create_sample_video, create_temp_dir


class VideoRendererTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = create_temp_dir("video_renderer_")
        cls.video_path = create_sample_video(cls.temp_dir / "sample.mp4")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_render_output_video_created(self) -> None:
        renderer = VideoRenderer()
        output_path = self.temp_dir / "final.mp4"
        work_dir = self.temp_dir / "render_work"
        clips = [
            {"src": str(self.video_path), "start": 0.0, "end": 0.8},
            {"src": str(self.video_path), "start": 1.0, "end": 1.8},
        ]
        result = renderer.render(clips=clips, output_path=str(output_path), work_dir=str(work_dir))
        self.assertEqual(result, str(output_path.resolve()))
        self.assertTrue(output_path.exists())
        self.assertGreater(output_path.stat().st_size, 0)

    def test_render_invalid_clip_raises(self) -> None:
        renderer = VideoRenderer()
        with self.assertRaises(RenderError):
            renderer.render(
                clips=[{"src": str(self.video_path), "start": 1.0, "end": 0.2}],
                output_path=str(self.temp_dir / "bad.mp4"),
                work_dir=str(self.temp_dir / "bad_render"),
            )


if __name__ == "__main__":
    unittest.main()
