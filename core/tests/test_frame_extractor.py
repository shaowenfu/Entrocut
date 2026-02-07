from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from process.frame_extractor import FrameExtractor
from tests.utils import create_sample_video, create_temp_dir


class FrameExtractorTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = create_temp_dir("frame_extractor_")
        cls.video_path = create_sample_video(cls.temp_dir / "sample.mp4")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_extract_frames_for_each_scene(self) -> None:
        extractor = FrameExtractor()
        scenes = [
            {"start_frame": 0, "end_frame": 24, "start_time": 0.0, "end_time": 1.0},
            {"start_frame": 24, "end_frame": 48, "start_time": 1.0, "end_time": 2.0},
        ]
        output_dir = self.temp_dir / "frames"
        result = extractor.extract(
            video_path=str(self.video_path),
            scenes=scenes,
            frames_per_scene=2,
            output_dir=str(output_dir),
        )
        self.assertEqual(len(result.extracted_frames), 4)
        for frame in result.extracted_frames:
            self.assertTrue(Path(frame.file_path).exists())
            self.assertGreaterEqual(frame.timestamp, 0.0)

    def test_extract_missing_video_raises(self) -> None:
        extractor = FrameExtractor()
        with self.assertRaises(FileNotFoundError):
            extractor.extract(
                video_path=str(self.temp_dir / "missing.mp4"),
                scenes=[],
                frames_per_scene=1,
            )

    def test_extract_invalid_frames_per_scene_raises(self) -> None:
        extractor = FrameExtractor()
        with self.assertRaises(ValueError):
            extractor.extract(
                video_path=str(self.video_path),
                scenes=[],
                frames_per_scene=0,
            )


if __name__ == "__main__":
    unittest.main()
