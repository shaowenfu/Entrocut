from __future__ import annotations

import asyncio
import os
import shutil
import time
import unittest
from unittest import mock
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


class _CrashDetector(_FakeDetector):
    def detect(self, video_path: str) -> DetectResult:
        raise RuntimeError("detector exploded")


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


class _InvalidEdlPayloadMockClient(_FakeMockClient):
    def generate_edl(self, job_id: str, video_path: str, segments, rule: str):
        return {
            "contract_version": self.contract_version,
            "job_id": job_id,
            "request_id": "req-invalid-edl",
            "edl": {
                "clips": [
                    {"src": "/tmp/not-exists-for-round2.mp4", "start": 0.0, "end": 1.0},
                ],
                "output_name": "final.mp4",
            },
        }


class _BadResponseErrorEdlMockClient(_FakeMockClient):
    def generate_edl(self, job_id: str, video_path: str, segments, rule: str):
        raise MockClientError(
            error_type="external_error",
            code="EXT_MOCK_BAD_RESPONSE",
            message="mock bad contract",
        )


class _FakeRenderer:
    def render(self, clips, output_path: str, work_dir: str) -> str:
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"video")
        return str(target)


class _EmptyRenderer:
    def render(self, clips, output_path: str, work_dir: str) -> str:
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")
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

    async def test_start_response_is_running_but_finally_failed_for_invalid_video(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        started = await orchestrator.start_job(video_path=str(self.temp_dir / "missing.mp4"))
        self.assertEqual(started["job_state"], "RUNNING")
        self.assertEqual(started["running_phase"], "VALIDATING_INPUT")
        self.assertIsNone(started["error"])

        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "FAILED")
        self.assertEqual(finished["error"]["code"], "VAL_VIDEO_NOT_FOUND")

    async def test_empty_video_path_fails_with_val_empty_input(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        started = await orchestrator.start_job(video_path="   ")
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "FAILED")
        self.assertEqual(finished["error"]["code"], "VAL_EMPTY_INPUT")

    async def test_unsupported_video_format_fails_with_val_video_format_unsupported(self) -> None:
        unsupported_video = self.temp_dir / "sample.txt"
        unsupported_video.write_text("not a video", encoding="utf-8")
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        started = await orchestrator.start_job(video_path=str(unsupported_video))
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "FAILED")
        self.assertEqual(finished["error"]["code"], "VAL_VIDEO_FORMAT_UNSUPPORTED")

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

    async def test_invalid_edl_payload_failed_in_generating_edl(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _InvalidEdlPayloadMockClient(base_url, version),
            enable_mock_fallback=True,
        )
        started = await orchestrator.start_job(video_path=str(self.video_path))
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "FAILED")
        self.assertEqual(finished["running_phase"], "GENERATING_EDL")
        self.assertEqual(finished["error"]["type"], "external_error")
        self.assertEqual(finished["error"]["code"], "EXT_MOCK_BAD_RESPONSE")

    async def test_bad_response_error_should_not_fallback(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _BadResponseErrorEdlMockClient(base_url, version),
            enable_mock_fallback=True,
        )
        started = await orchestrator.start_job(video_path=str(self.video_path))
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "FAILED")
        self.assertEqual(finished["running_phase"], "GENERATING_EDL")
        self.assertEqual(finished["error"]["type"], "external_error")
        self.assertEqual(finished["error"]["code"], "EXT_MOCK_BAD_RESPONSE")

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

    async def test_cancel_active_pipeline_marks_failed_with_cancel_code(self) -> None:
        class _CancellableRunBlockingOrchestrator(JobOrchestrator):
            async def _run_blocking(self, func, *args):  # type: ignore[override]
                await asyncio.sleep(0.3)
                return func(*args)

        orchestrator = _CancellableRunBlockingOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        started = await orchestrator.start_job(video_path=str(self.video_path))
        await asyncio.sleep(0.05)
        await orchestrator.cancel_job(started["job_id"])
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "FAILED")
        self.assertEqual(finished["error"]["code"], "RUN_CANCELLED_BY_USER")
        self.assertEqual(finished["error"]["type"], "runtime_error")

    async def test_unhandled_exception_maps_to_run_unhandled_exception(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _CrashDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_FakeRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        started = await orchestrator.start_job(video_path=str(self.video_path))
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "FAILED")
        self.assertEqual(finished["error"]["type"], "runtime_error")
        self.assertEqual(finished["error"]["code"], "RUN_UNHANDLED_EXCEPTION")
        self.assertEqual(finished["error"]["step"], "UNKNOWN")

    async def test_empty_rendered_output_fails_with_run_render_failed(self) -> None:
        orchestrator = JobOrchestrator(
            work_root=str(self.temp_dir / "jobs"),
            use_background_threads=False,
            detector_factory=lambda threshold, min_len: _FakeDetector(threshold, min_len),
            extractor_factory=_FakeExtractor,
            renderer=_EmptyRenderer(),
            mock_client_factory=lambda base_url, version: _FakeMockClient(base_url, version),
        )
        started = await orchestrator.start_job(video_path=str(self.video_path))
        finished = await orchestrator.wait_for_completion(started["job_id"], timeout=5.0)
        self.assertEqual(finished["job_state"], "FAILED")
        self.assertEqual(finished["running_phase"], "RENDERING_OUTPUT")
        self.assertEqual(finished["error"]["type"], "runtime_error")
        self.assertEqual(finished["error"]["code"], "RUN_RENDER_FAILED")
        self.assertIn("empty", finished["error"]["message"])


class JobOrchestratorWorkRootResolutionTestCase(unittest.TestCase):
    def test_no_env_uses_repo_local_entrocut_jobs(self) -> None:
        repo_root = create_temp_dir("repo_root_no_env_")
        try:
            for dir_name in ("client", "core", "server", "docs"):
                (repo_root / dir_name).mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("process.job_orchestrator._detect_repo_root", return_value=repo_root):
                    orchestrator = JobOrchestrator()
            self.assertEqual(orchestrator.work_root, (repo_root / "entrocut_jobs").resolve())
        finally:
            shutil.rmtree(repo_root, ignore_errors=True)

    def test_dev_env_uses_repo_local_entrocut_jobs(self) -> None:
        repo_root = create_temp_dir("repo_root_")
        try:
            for dir_name in ("client", "core", "server", "docs"):
                (repo_root / dir_name).mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"CORE_RUNTIME_ENV": "development"}, clear=False):
                with mock.patch("process.job_orchestrator._detect_repo_root", return_value=repo_root):
                    orchestrator = JobOrchestrator()
            self.assertEqual(orchestrator.work_root, (repo_root / "entrocut_jobs").resolve())
        finally:
            shutil.rmtree(repo_root, ignore_errors=True)

    def test_prod_env_keeps_tmp_work_root(self) -> None:
        with mock.patch.dict(os.environ, {"CORE_RUNTIME_ENV": "production"}, clear=False):
            with mock.patch("process.job_orchestrator._detect_repo_root", return_value=self._fake_repo_root()):
                orchestrator = JobOrchestrator()
        self.assertEqual(orchestrator.work_root, Path("/tmp/entrocut_jobs").resolve())

    def test_explicit_core_work_root_has_highest_priority(self) -> None:
        custom_root = create_temp_dir("custom_work_root_")
        try:
            with mock.patch.dict(
                os.environ,
                {"CORE_RUNTIME_ENV": "production", "CORE_WORK_ROOT": str(custom_root)},
                clear=False,
            ):
                with mock.patch("process.job_orchestrator._detect_repo_root", return_value=self._fake_repo_root()):
                    orchestrator = JobOrchestrator()
            self.assertEqual(orchestrator.work_root, custom_root.resolve())
        finally:
            shutil.rmtree(custom_root, ignore_errors=True)

    def test_legacy_entrocut_jobs_root_is_supported(self) -> None:
        legacy_root = create_temp_dir("legacy_work_root_")
        try:
            with mock.patch.dict(os.environ, {"ENTROCUT_JOBS_ROOT": str(legacy_root)}, clear=True):
                orchestrator = JobOrchestrator()
            self.assertEqual(orchestrator.work_root, legacy_root.resolve())
        finally:
            shutil.rmtree(legacy_root, ignore_errors=True)

    def test_core_work_root_takes_precedence_over_legacy_env(self) -> None:
        core_root = create_temp_dir("core_work_root_")
        legacy_root = create_temp_dir("legacy_work_root_")
        try:
            with mock.patch.dict(
                os.environ,
                {"CORE_WORK_ROOT": str(core_root), "ENTROCUT_JOBS_ROOT": str(legacy_root)},
                clear=True,
            ):
                orchestrator = JobOrchestrator()
            self.assertEqual(orchestrator.work_root, core_root.resolve())
        finally:
            shutil.rmtree(core_root, ignore_errors=True)
            shutil.rmtree(legacy_root, ignore_errors=True)

    @staticmethod
    def _fake_repo_root() -> Path:
        return Path("/tmp/entrocut_fake_repo")


if __name__ == "__main__":
    unittest.main()
