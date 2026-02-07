"""
Core 任务编排器

负责驱动 T1 状态机、调度本地算法流程、调用远端 Mock，并产出最终视频。
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from detect.scene_detector import DetectResult, SceneDetector
from process.frame_extractor import ExtractResult, FrameExtractor
from process.mock_client import MockClientError, MockServerClient
from process.video_renderer import RenderError, VideoRenderer


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_log(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


@dataclass
class JobError:
    type: str
    code: str
    message: str
    step: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JobArtifacts:
    workdir: str = ""
    scenes_json: str = ""
    frames_dir: str = ""
    analysis_json: str = ""
    edl_json: str = ""
    output_video: str = ""


@dataclass
class JobStatus:
    job_id: str
    video_path: str
    job_state: str = "IDLE"
    running_phase: Optional[str] = None
    progress: int = 0
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    finished_at: Optional[str] = None
    error: Optional[JobError] = None
    artifacts: JobArtifacts = field(default_factory=JobArtifacts)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PipelineError(Exception):
    """编排错误，包含统一错误语义。"""

    def __init__(
        self,
        error_type: str,
        code: str,
        message: str,
        step: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.code = code
        self.step = step
        self.details = details or {}


class JobOrchestrator:
    """
    Core 任务编排器（单活任务版本）。
    """

    def __init__(
        self,
        work_root: Optional[str] = None,
        default_server_base_url: Optional[str] = None,
        default_contract_version: str = "0.1.0-mock",
        default_rule: str = "highlight_first",
        enable_mock_fallback: bool = True,
        use_background_threads: bool = True,
        detector_factory: Optional[Callable[[float, int], SceneDetector]] = None,
        extractor_factory: Optional[Callable[[], FrameExtractor]] = None,
        renderer: Optional[VideoRenderer] = None,
        mock_client_factory: Optional[Callable[[Optional[str], str], MockServerClient]] = None,
    ):
        self.work_root = Path(
            work_root
            or os.getenv("CORE_WORK_ROOT")
            or "/tmp/entrocut_jobs"
        ).expanduser().resolve()
        self.default_server_base_url = default_server_base_url or os.getenv("MOCK_SERVER_BASE_URL")
        self.default_contract_version = default_contract_version
        self.default_rule = default_rule
        self.enable_mock_fallback = enable_mock_fallback
        self.use_background_threads = use_background_threads

        self._detector_factory = detector_factory or (lambda threshold, min_len: SceneDetector(threshold, min_len))
        self._extractor_factory = extractor_factory or FrameExtractor
        self._renderer = renderer or VideoRenderer()
        self._mock_client_factory = mock_client_factory or (
            lambda base_url, version: MockServerClient(base_url=base_url, contract_version=version)
        )

        self._lock = asyncio.Lock()
        self._jobs: Dict[str, JobStatus] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._active_job_id: Optional[str] = None

    async def start_job(
        self,
        video_path: str,
        frames_per_scene: int = 3,
        threshold: float = 27.0,
        min_scene_length: int = 15,
        server_base_url: Optional[str] = None,
        contract_version: Optional[str] = None,
        rule: Optional[str] = None,
    ) -> Dict[str, Any]:
        async with self._lock:
            if self._active_job_id:
                raise PipelineError(
                    error_type="runtime_error",
                    code="RUN_JOB_ALREADY_ACTIVE",
                    message=f"Active job exists: {self._active_job_id}",
                    step="START_JOB",
                )

            job_id = str(uuid.uuid4())
            job = JobStatus(job_id=job_id, video_path=str(Path(video_path).expanduser().resolve()))
            job.job_state = "RUNNING"
            job.running_phase = "VALIDATING_INPUT"
            job.progress = 5
            job.updated_at = _now_iso()

            self._jobs[job_id] = job
            self._active_job_id = job_id
            self.work_root.mkdir(parents=True, exist_ok=True)

            self._tasks[job_id] = asyncio.create_task(
                self._run_job(
                    job_id=job_id,
                    video_path=job.video_path,
                    frames_per_scene=frames_per_scene,
                    threshold=threshold,
                    min_scene_length=min_scene_length,
                    server_base_url=server_base_url,
                    contract_version=contract_version or self.default_contract_version,
                    rule=rule or self.default_rule,
                )
            )

            self._emit_event(job_id, "JOB_STATE_CHANGED", {"job_state": job.job_state, "running_phase": job.running_phase})
            return job.to_dict()

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job not found: {job_id}")
            return job.to_dict()

    async def list_jobs(self) -> List[Dict[str, Any]]:
        async with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    async def cancel_job(self, job_id: str) -> Dict[str, Any]:
        async with self._lock:
            task = self._tasks.get(job_id)
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job not found: {job_id}")
            if job.job_state != "RUNNING":
                return job.to_dict()
            if task and not task.done():
                task.cancel()
            return job.to_dict()

    async def wait_for_completion(self, job_id: str, timeout: float = 60.0) -> Dict[str, Any]:
        started_at = asyncio.get_running_loop().time()

        async def _wait():
            while True:
                status = await self.get_job(job_id)
                if status["job_state"] in {"SUCCEEDED", "FAILED"}:
                    return status
                await asyncio.sleep(0.05)

        await asyncio.wait_for(_wait(), timeout=timeout)

        # 状态进入终态后，继续等待后台 Task 彻底结束，避免测试与关闭阶段悬挂。
        async with self._lock:
            task = self._tasks.get(job_id)
        if task and not task.done():
            elapsed = asyncio.get_running_loop().time() - started_at
            remaining = max(0.1, timeout - elapsed)
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=remaining)
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        return await self.get_job(job_id)

    async def _run_job(
        self,
        *,
        job_id: str,
        video_path: str,
        frames_per_scene: int,
        threshold: float,
        min_scene_length: int,
        server_base_url: Optional[str],
        contract_version: str,
        rule: str,
    ) -> None:
        try:
            self._validate_input(video_path, frames_per_scene, threshold, min_scene_length)
            job_dir = self.work_root / job_id
            frames_dir = job_dir / "frames"
            render_dir = job_dir / "render"
            job_dir.mkdir(parents=True, exist_ok=True)
            await self._update_artifacts(job_id, {"workdir": str(job_dir)})

            await self._update_phase(job_id, "DETECTING_SCENES", 20)
            detector = self._detector_factory(threshold, min_scene_length)
            detect_result: DetectResult = await self._run_blocking(detector.detect, video_path)
            if not detect_result.scenes:
                raise PipelineError(
                    error_type="runtime_error",
                    code="RUN_SCENE_DETECT_FAILED",
                    message="No scenes detected",
                    step="DETECTING_SCENES",
                )

            scenes_payload = [asdict(scene) for scene in detect_result.scenes]
            scenes_json_path = job_dir / "scenes.json"
            await self._run_blocking(self._write_json_file, scenes_json_path, {
                "total_frames": detect_result.total_frames,
                "fps": detect_result.fps,
                "duration": detect_result.duration,
                "scenes": scenes_payload,
            })
            await self._update_artifacts(job_id, {"scenes_json": str(scenes_json_path)})

            await self._update_phase(job_id, "EXTRACTING_FRAMES", 40)
            extractor = self._extractor_factory()
            extract_result: ExtractResult = await self._run_blocking(
                extractor.extract,
                video_path,
                scenes_payload,
                frames_per_scene,
                str(frames_dir),
            )
            frames_payload = [asdict(frame) for frame in extract_result.extracted_frames]
            if not frames_payload:
                raise PipelineError(
                    error_type="runtime_error",
                    code="RUN_FRAME_EXTRACT_FAILED",
                    message="No frames extracted",
                    step="EXTRACTING_FRAMES",
                )
            await self._update_artifacts(job_id, {"frames_dir": str(frames_dir)})
            await self._run_blocking(self._write_json_file, job_dir / "frames.json", {"frames": frames_payload})

            await self._update_phase(job_id, "ANALYZING_MOCK", 55)
            mock_client = self._mock_client_factory(
                server_base_url or self.default_server_base_url,
                contract_version,
            )
            analysis_response = await self._analyze_with_fallback(
                mock_client=mock_client,
                job_id=job_id,
                video_path=video_path,
                frames=frames_payload,
            )
            analysis_json_path = job_dir / "analysis.json"
            await self._run_blocking(self._write_json_file, analysis_json_path, analysis_response)
            await self._update_artifacts(job_id, {"analysis_json": str(analysis_json_path)})
            segments = analysis_response.get("analysis", {}).get("segments", [])
            if not segments:
                raise PipelineError(
                    error_type="runtime_error",
                    code="RUN_MOCK_DATA_GENERATION_FAILED",
                    message="No segments returned from analysis",
                    step="ANALYZING_MOCK",
                )

            await self._update_phase(job_id, "GENERATING_EDL", 70)
            edl_response = await self._edl_with_fallback(
                mock_client=mock_client,
                job_id=job_id,
                video_path=video_path,
                segments=segments,
                rule=rule,
            )
            clips = self._validate_edl_response(edl_response)
            edl_json_path = job_dir / "edl.json"
            await self._run_blocking(self._write_json_file, edl_json_path, edl_response)
            await self._update_artifacts(job_id, {"edl_json": str(edl_json_path)})

            await self._update_phase(job_id, "RENDERING_OUTPUT", 95)
            output_video = str(job_dir / "final.mp4")
            try:
                await self._run_blocking(self._renderer.render, clips, output_video, str(render_dir))
            except RenderError as exc:
                raise PipelineError(
                    error_type="runtime_error",
                    code="RUN_RENDER_FAILED",
                    message=str(exc),
                    step="RENDERING_OUTPUT",
                ) from exc

            if not Path(output_video).exists():
                raise PipelineError(
                    error_type="runtime_error",
                    code="RUN_RENDER_FAILED",
                    message="Rendered output file not found",
                    step="RENDERING_OUTPUT",
                )

            await self._update_phase(job_id, "FINALIZING_RESULT", 100)
            await self._mark_succeeded(job_id, output_video)
        except asyncio.CancelledError:
            await self._mark_failed(
                job_id=job_id,
                error=JobError(
                    type="runtime_error",
                    code="RUN_CANCELLED_BY_USER",
                    message="Job cancelled by user",
                    step="CANCEL_JOB",
                ),
            )
            raise
        except PipelineError as exc:
            await self._mark_failed(
                job_id=job_id,
                error=JobError(
                    type=exc.error_type,
                    code=exc.code,
                    message=str(exc),
                    step=exc.step,
                    details=exc.details,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            await self._mark_failed(
                job_id=job_id,
                error=JobError(
                    type="runtime_error",
                    code="RUN_UNEXPECTED_ERROR",
                    message=str(exc),
                    step="UNKNOWN",
                ),
            )
        finally:
            async with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None

    def _validate_input(
        self,
        video_path: str,
        frames_per_scene: int,
        threshold: float,
        min_scene_length: int,
    ) -> None:
        source = Path(video_path).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise PipelineError(
                error_type="validation_error",
                code="VAL_VIDEO_NOT_FOUND",
                message=f"Video file not found: {video_path}",
                step="VALIDATING_INPUT",
            )
        if frames_per_scene <= 0:
            raise PipelineError(
                error_type="validation_error",
                code="VAL_EMPTY_INPUT",
                message="frames_per_scene must be greater than 0",
                step="VALIDATING_INPUT",
            )
        if threshold <= 0:
            raise PipelineError(
                error_type="validation_error",
                code="VAL_EMPTY_INPUT",
                message="threshold must be greater than 0",
                step="VALIDATING_INPUT",
            )
        if min_scene_length <= 0:
            raise PipelineError(
                error_type="validation_error",
                code="VAL_EMPTY_INPUT",
                message="min_scene_length must be greater than 0",
                step="VALIDATING_INPUT",
            )

    async def _analyze_with_fallback(
        self,
        *,
        mock_client: MockServerClient,
        job_id: str,
        video_path: str,
        frames: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            return await self._run_blocking(mock_client.analyze, job_id, video_path, frames)
        except MockClientError as exc:
            if self.enable_mock_fallback and self._can_fallback_for_external_error(exc):
                self._emit_event(
                    job_id,
                    "MOCK_ANALYZE_FALLBACK",
                    {"code": exc.code, "message": str(exc)},
                )
                return mock_client.local_fallback_analyze(job_id=job_id, video_path=video_path, frames=frames)
            raise PipelineError(
                error_type=exc.error_type,
                code=exc.code,
                message=str(exc),
                step="ANALYZING_MOCK",
                details=exc.details,
            ) from exc

    async def _edl_with_fallback(
        self,
        *,
        mock_client: MockServerClient,
        job_id: str,
        video_path: str,
        segments: List[Dict[str, Any]],
        rule: str,
    ) -> Dict[str, Any]:
        try:
            return await self._run_blocking(mock_client.generate_edl, job_id, video_path, segments, rule)
        except MockClientError as exc:
            if self.enable_mock_fallback and self._can_fallback_for_external_error(exc):
                self._emit_event(
                    job_id,
                    "MOCK_EDL_FALLBACK",
                    {"code": exc.code, "message": str(exc)},
                )
                return mock_client.local_fallback_edl(
                    job_id=job_id,
                    video_path=video_path,
                    segments=segments,
                    rule=rule,
                )
            raise PipelineError(
                error_type=exc.error_type,
                code=exc.code,
                message=str(exc),
                step="GENERATING_EDL",
                details=exc.details,
            ) from exc

    @staticmethod
    def _can_fallback_for_external_error(exc: MockClientError) -> bool:
        if exc.error_type != "external_error":
            return False
        return exc.code in {"EXT_MOCK_UNAVAILABLE", "EXT_MOCK_TIMEOUT"}

    @staticmethod
    def _validate_edl_response(edl_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        edl = edl_response.get("edl")
        if not isinstance(edl, dict):
            raise PipelineError(
                error_type="external_error",
                code="EXT_MOCK_BAD_RESPONSE",
                message="Invalid EDL response: missing edl object",
                step="GENERATING_EDL",
            )

        clips = edl.get("clips")
        if not isinstance(clips, list) or not clips:
            raise PipelineError(
                error_type="external_error",
                code="EXT_MOCK_BAD_RESPONSE",
                message="Invalid EDL response: clips must be a non-empty list",
                step="GENERATING_EDL",
            )

        normalized: List[Dict[str, Any]] = []
        for idx, clip in enumerate(clips):
            if not isinstance(clip, dict):
                raise PipelineError(
                    error_type="external_error",
                    code="EXT_MOCK_BAD_RESPONSE",
                    message=f"Invalid EDL response: clip[{idx}] is not an object",
                    step="GENERATING_EDL",
                )

            src = clip.get("src")
            start = clip.get("start")
            end = clip.get("end")
            if not isinstance(src, str) or not src.strip():
                raise PipelineError(
                    error_type="external_error",
                    code="EXT_MOCK_BAD_RESPONSE",
                    message=f"Invalid EDL response: clip[{idx}].src is required",
                    step="GENERATING_EDL",
                )
            src_path = Path(src).expanduser().resolve()
            if not src_path.exists() or not src_path.is_file():
                raise PipelineError(
                    error_type="external_error",
                    code="EXT_MOCK_BAD_RESPONSE",
                    message=f"Invalid EDL response: clip[{idx}].src not found: {src}",
                    step="GENERATING_EDL",
                )
            try:
                start_value = float(start)
                end_value = float(end)
            except (TypeError, ValueError) as exc:
                raise PipelineError(
                    error_type="external_error",
                    code="EXT_MOCK_BAD_RESPONSE",
                    message=f"Invalid EDL response: clip[{idx}] start/end must be numbers",
                    step="GENERATING_EDL",
                ) from exc
            if end_value <= start_value:
                raise PipelineError(
                    error_type="external_error",
                    code="EXT_MOCK_BAD_RESPONSE",
                    message=f"Invalid EDL response: clip[{idx}] end must be greater than start",
                    step="GENERATING_EDL",
                )
            normalized.append(
                {
                    "src": str(src_path),
                    "start": start_value,
                    "end": end_value,
                    **{k: v for k, v in clip.items() if k not in {"src", "start", "end"}},
                }
            )
        return normalized

    async def _update_phase(self, job_id: str, running_phase: str, progress: int) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.running_phase = running_phase
            job.progress = progress
            job.updated_at = _now_iso()
            self._emit_event(
                job_id,
                "JOB_PROGRESS_UPDATED",
                {"running_phase": running_phase, "progress": progress, "job_state": job.job_state},
            )

    async def _update_artifacts(self, job_id: str, patch: Dict[str, Any]) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            for key, value in patch.items():
                setattr(job.artifacts, key, value)
            job.updated_at = _now_iso()

    async def _mark_failed(self, job_id: str, error: JobError) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.job_state = "FAILED"
            job.error = error
            job.finished_at = _now_iso()
            job.updated_at = job.finished_at
            self._emit_event(
                job_id,
                "JOB_FAILED",
                {
                    "job_state": job.job_state,
                    "running_phase": job.running_phase,
                    "error_code": error.code,
                    "error_type": error.type,
                },
            )

    async def _mark_succeeded(self, job_id: str, output_video: str) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            job.job_state = "SUCCEEDED"
            job.running_phase = "FINALIZING_RESULT"
            job.progress = 100
            job.error = None
            job.artifacts.output_video = output_video
            job.finished_at = _now_iso()
            job.updated_at = job.finished_at
        self._emit_event(
            job_id,
            "JOB_COMPLETED",
            {"job_state": job.job_state, "output_video": output_video},
        )

    async def _run_blocking(self, func: Callable[..., Any], *args) -> Any:
        if self.use_background_threads:
            return await asyncio.to_thread(func, *args)
        return func(*args)

    @staticmethod
    def _write_json_file(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _emit_event(job_id: str, event: str, payload: Dict[str, Any]) -> None:
        _json_log(
            {
                "timestamp": _now_iso(),
                "level": "INFO",
                "job_id": job_id,
                "event": event,
                **payload,
            }
        )
