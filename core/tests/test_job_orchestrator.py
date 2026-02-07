from __future__ import annotations

import asyncio
import shutil
import time
import unittest
from pathlib import Path

from detect.scene_detector import DetectResult, SceneSegment
from process.frame_extractor import ExtractResult, ExtractedFrame
from process.job_orchestrator import JobOrchestrator, JobStatus, PipelineError
from process.mock_client import MockClientError
from tests.utils import create_sample_video, create_temp_dir


class _FakeDetector:
    def __init__(self, threshold: float, min_scene_length: int):
        self.threshold = threshold
        self.min_scene_length = min_scene_length

    def detect(self, video_path: str) -> DetectResult:
        return DetectResult(
            total_frames=60,
            fps=30.0,
            duration=2.0,
            scenes=[
                SceneSegment(start_frame=0, end_frame=30, start_time=0.0, end_time=1.0),
                SceneSegment(start_frame=30, end_frame=60, start_time=1.0, end_time=2.0),
            ],
        )


class _SlowDetector(_FakeDetector):
    def detect(self, video_path: str) -> DetectResult:
        time.sleep(0.3)
        return super().detect(video_path)


class _FakeExtractor:
    def extract(self, video_path: str, scenes, frames_per_scene: int, output_dir: str) -> ExtractResult:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = Path(output_dir) / "f_001.jpg"
        output_path.write_bytes(b"frame")
        return ExtractResult(
            video_path=video_path,
            extracted_frames=[
                ExtractedFrame(scene_index=0, frame_number=5, timestamp=0.2, file_path=str(output_path)),
                ExtractedFrame(scene_index=1, frame_number=35, timestamp=1.2, file_path=str(output_path)),
            ],
        )


class _FakeMockClient:
    def __init__(self, base_url: str | None, contract_version: str):
        self.base_url = base_url
        self.contract_version = contract_version

    def analyze(self, job_id: str, video_path: str, frames):
        return {
            "contract_version": self.contract_version,
            "job_id": job_id,
            "request_id": "req-1",
            "analysis": {
                "segments": [
                    {"segment_id": "seg-1", "start_time": 0.0, "end_time": 1.0, "tags": ["a"]},
                    {"segment_id": "seg-2", "start_time": 1.0, "end_time": 2.0, "tags": ["b"]},
                ]
            },
        }

    def generate_edl(self, job_id: str, video_path: str, segments, rule: str):
        return {
            "contract_version": self.contract_version,
            "job_id": job_id,
            "request_id": "req-2",
            "edl": {
                "clips": [
                    {"src": video_path, "start": 0.0, "end": 0.8},
                    {"src": video_path, "start": 1.0, "end": 1.8},
                ],
                "output_name": "final.mp4",
            },
        }

    def local_fallback_analyze(self, job_id: str, video_path: str, frames):
        return self.analyze(job_id, video_path, frames)

    def local_fallback_edl(self, job_id: str, video_path: str, segments, rule: str):
        return self.generate_edl(job_id, video_path, segments, rule)


class _ExternalFailMockClient(_FakeMockClient):
    def analyze(self, job_id: str, video_path: str, frames):
        raise MockClientError(
            error_type="external_error",
            code="EXT_MOCK_UNAVAILABLE",
            message="mock down",
        )

    def local_fallback_analyze(self, job_id: str, video_path: str, frames):
        return _FakeMockClient.analyze(self, job_id, video_path, frames)


class _FakeRenderer:
    def render(self, clips, output_path: str, work_dir: str) -> str:
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"video")
        return str(target)


class JobOrchestratorTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = create_temp_dir("orchestrator_")
        self.video_path = self.temp_dir / "sample.mp4"
        self.video_path.write_bytes(b"fake video")

    async def asyncTearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_job_pipeline_success(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        started = await orchestrator.start_job(video_path=str(self.video_path))
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "SUCCEEDED")
        self.assertEqual(finished["progress"], 100)
        self.assertTrue(Path(finished["artifacts"]["output_video"]).exists())

    async def test_job_validation_failure(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        started = await orchestrator.start_job(video_path=str(self.temp_dir / "missing.mp4"))
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "FAILED")
        self.assertEqual(finished["error"]["code"], "VAL_VIDEO_NOT_FOUND")

    async def test_single_active_job_enforced(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _SlowDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        started = await orchestrator.start_job(video_path=str(self.video_path))
        with self.assertRaises(PipelineError) as ctx:
            await orchestrator.start_job(video_path=str(self.video_path))
        self.assertEqual(ctx.exception.code, "RUN_JOB_ALREADY_ACTIVE")
        await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)

    async def test_job_pipeline_with_real_components(self) -> None:
        real_video = create_sample_video(self.temp_dir / "real_sample.mp4")
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs_real"),
            use_background_threads=False,
            enable_mock_fallback=True,
            default_server_base_url=None,
        )
        started = await orchestrator.start_job(
            video_path=str(real_video),
            frames_per_scene=2,
            threshold=8.0,
            min_scene_length=5,
        )
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=20.0)
        self.assertEqual(finished["job_state"], "SUCCEEDED")
        self.assertTrue(Path(finished["artifacts"]["scenes_json"]).exists())
        self.assertTrue(Path(finished["artifacts"]["frames_dir"]).exists())
        self.assertTrue(Path(finished["artifacts"]["analysis_json"]).exists())
        self.assertTrue(Path(finished["artifacts"]["edl_json"]).exists())
        self.assertTrue(Path(finished["artifacts"]["output_video"]).exists())

    async def test_external_error_fallback_enabled(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _ExternalFailMockClient(base_url, version),
            enable_mock_fallback=True,
        )
        started = await orchestrator.start_job(video_path=str(self.video_path))
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "SUCCEEDED")

    async def test_cancel_running_job(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        running_job = JobStatus(
            job_id="job-cancel-1",
            video_path=str(self.video_path),
            job_state="RUNNING",
            running_phase="DETECTING_SCENES",
            progress=20,
        )
        background_task = asyncio.create_task(asyncio.sleep(30))
        orchestrator._jobs[running_job.job_id] = running_job  # pylint: disable=protected-access
        orchestrator._tasks[running_job.job_id] = background_task  # pylint: disable=protected-access

        status = await orchestrator.cancel_job(running_job.job_id)
        await asyncio.sleep(0)
        self.assertEqual(status["job_state"], "RUNNING")
        self.assertTrue(background_task.cancelled() or background_task.done())


if __name__ == "__main__":
    unittest.main()
