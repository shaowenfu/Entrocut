from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from detect.scene_detector import SceneDetector
from tests.utils import create_sample_video, create_temp_dir


class SceneDetectorTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = create_temp_dir("scene_detector_")
        cls.video_path = create_sample_video(cls.temp_dir / "sample.mp4")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_detect_returns_basic_metadata(self) -> None:
        detector = SceneDetector(threshold=8.0, min_scene_length=5)
        result = detector.detect(str(self.video_path))
        self.assertGreater(result.fps, 0)
        self.assertGreater(result.total_frames, 0)
        self.assertGreater(result.duration, 0)

    def test_detect_returns_non_empty_scenes(self) -> None:
        detector = SceneDetector(threshold=8.0, min_scene_length=5)
        result = detector.detect(str(self.video_path))
        self.assertGreaterEqual(len(result.scenes), 1)
        for scene in result.scenes:
            self.assertLess(scene.start_time, scene.end_time)
            self.assertLess(scene.start_frame, scene.end_frame)

    def test_detect_missing_file_raises(self) -> None:
        detector = SceneDetector()
        with self.assertRaises(FileNotFoundError):
            detector.detect(str(Path(self.temp_dir) / "not_exists.mp4"))


if __name__ == "__main__":
    unittest.main()
