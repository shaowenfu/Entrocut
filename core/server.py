"""
Entrocut Core - 本地算法 Sidecar 服务

提供视频处理、场景检测、抽帧等功能的核心算法服务。
运行在本地，与 Electron 主进程通信。
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
import uvicorn
from pathlib import Path

from detect.scene_detector import SceneDetector
from process.frame_extractor import FrameExtractor
from process.job_orchestrator import JobOrchestrator, PipelineError


# ============================================
# Request/Response Models
# ============================================

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str
    version: str


class DetectScenesRequest(BaseModel):
    """场景检测请求"""
    video_path: str
    threshold: Optional[float] = 27.0
    min_scene_length: Optional[int] = 15


class SceneSegment(BaseModel):
    """场景片段"""
    start_frame: int
    end_frame: int
    start_time: float  # 秒
    end_time: float    # 秒


class DetectScenesResponse(BaseModel):
    """场景检测响应"""
    total_frames: int
    fps: float
    duration: float
    scenes: List[SceneSegment]


class ExtractFramesRequest(BaseModel):
    """抽帧请求"""
    video_path: str
    scenes: List[SceneSegment]
    frames_per_scene: int = 3


class ExtractedFrame(BaseModel):
    """提取的帧"""
    scene_index: int
    frame_number: int
    timestamp: float
    file_path: str


class ExtractFramesResponse(BaseModel):
    """抽帧响应"""
    video_path: str
    extracted_frames: List[ExtractedFrame]


class StartJobRequest(BaseModel):
    """启动任务请求"""

    video_path: str
    frames_per_scene: int = 3
    threshold: float = 27.0
    min_scene_length: int = 15
    server_base_url: Optional[str] = None
    contract_version: str = "0.1.0-mock"
    rule: str = "highlight_first"


class JobErrorModel(BaseModel):
    """任务错误信息"""

    type: str
    code: str
    message: str
    step: str
    details: Dict[str, Any] = Field(default_factory=dict)


class JobArtifactsModel(BaseModel):
    """任务产物路径"""

    workdir: str = ""
    scenes_json: str = ""
    frames_dir: str = ""
    analysis_json: str = ""
    edl_json: str = ""
    output_video: str = ""


class JobStatusResponse(BaseModel):
    """任务状态响应"""

    job_id: str
    video_path: str
    job_state: str
    running_phase: Optional[str] = None
    progress: int
    created_at: str
    updated_at: str
    finished_at: Optional[str] = None
    error: Optional[JobErrorModel] = None
    artifacts: JobArtifactsModel


class CancelJobResponse(BaseModel):
    """取消任务响应"""

    job_id: str
    job_state: str
    running_phase: Optional[str] = None
    progress: int


class ErrorModel(BaseModel):
    """统一错误响应"""

    type: str
    code: str
    message: str
    step: str
    details: Dict[str, Any] = Field(default_factory=dict)
    request_id: str
    timestamp: str


class ErrorEnvelope(BaseModel):
    error: ErrorModel


class CoreApiError(Exception):
    """Core API 显式错误。"""

    def __init__(
        self,
        *,
        status_code: int,
        error_type: str,
        code: str,
        message: str,
        step: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.code = code
        self.message = message
        self.step = step
        self.details = details or {}


# ============================================
# Application Lifecycle
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    print("🚀 Entrocut Core Sidecar starting...")
    yield
    # 关闭时清理
    print("👋 Entrocut Core Sidecar shutting down...")


app = FastAPI(
    title="Entrocut Core",
    description="本地算法 Sidecar 服务 - 视频场景检测与抽帧",
    version="0.1.0",
    lifespan=lifespan
)
orchestrator = JobOrchestrator()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_id_from_state(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if isinstance(value, str) and value:
        return value
    fallback = str(uuid.uuid4())
    request.state.request_id = fallback
    return fallback


def _error_payload(
    *,
    request: Request,
    error_type: str,
    code: str,
    message: str,
    step: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "error": {
            "type": error_type,
            "code": code,
            "message": message,
            "step": step,
            "details": details or {},
            "request_id": _request_id_from_state(request),
            "timestamp": _now_iso(),
        }
    }


# ============================================
# Endpoints
# ============================================

@app.middleware("http")
async def request_tracking_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="ok",
        service="entrocut-core",
        version="0.1.0"
    )


@app.post("/detect-scenes", response_model=DetectScenesResponse)
async def detect_scenes(request: DetectScenesRequest):
    """
    场景检测

    使用 PySceneDetect 检测视频中的场景切换点。
    """
    try:
        detector = SceneDetector(
            threshold=request.threshold,
            min_scene_length=request.min_scene_length
        )
        result = detector.detect(request.video_path)
        return result
    except FileNotFoundError as exc:
        raise CoreApiError(
            status_code=404,
            error_type="validation_error",
            code="VAL_VIDEO_NOT_FOUND",
            message=f"Video file not found: {request.video_path}",
            step="DETECTING_SCENES",
        ) from exc
    except Exception as exc:
        raise CoreApiError(
            status_code=500,
            error_type="runtime_error",
            code="RUN_SCENE_DETECT_FAILED",
            message=f"Scene detection failed: {str(exc)}",
            step="DETECTING_SCENES",
        ) from exc


@app.post("/extract-frames", response_model=ExtractFramesResponse)
async def extract_frames(request: ExtractFramesRequest):
    """
    从视频中抽取关键帧

    根据 scene 切分点，从每个场景中抽取指定数量的帧。
    """
    try:
        extractor = FrameExtractor()
        result = extractor.extract(
            video_path=request.video_path,
            scenes=request.scenes,
            frames_per_scene=request.frames_per_scene
        )
        return result
    except FileNotFoundError as exc:
        raise CoreApiError(
            status_code=404,
            error_type="validation_error",
            code="VAL_VIDEO_NOT_FOUND",
            message=f"Video file not found: {request.video_path}",
            step="EXTRACTING_FRAMES",
        ) from exc
    except Exception as exc:
        raise CoreApiError(
            status_code=500,
            error_type="runtime_error",
            code="RUN_FRAME_EXTRACT_FAILED",
            message=f"Frame extraction failed: {str(exc)}",
            step="EXTRACTING_FRAMES",
        ) from exc


@app.post("/jobs/start", response_model=JobStatusResponse)
async def start_job(request: StartJobRequest):
    """
    启动端到端处理任务
    """
    try:
        status = await orchestrator.start_job(
            video_path=request.video_path,
            frames_per_scene=request.frames_per_scene,
            threshold=request.threshold,
            min_scene_length=request.min_scene_length,
            server_base_url=request.server_base_url,
            contract_version=request.contract_version,
            rule=request.rule,
        )
        return status
    except PipelineError as exc:
        if exc.code == "RUN_JOB_ALREADY_ACTIVE":
            status_code = 409
        elif exc.error_type == "validation_error":
            status_code = 400
        elif exc.error_type == "external_error":
            status_code = 502
        else:
            status_code = 500

        raise CoreApiError(
            status_code=status_code,
            error_type=exc.error_type,
            code=exc.code,
            message=str(exc),
            step=exc.step,
            details=exc.details,
        ) from exc


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str):
    """查询任务状态"""
    try:
        return await orchestrator.get_job(job_id)
    except KeyError as exc:
        raise CoreApiError(
            status_code=404,
            error_type="validation_error",
            code="VAL_JOB_NOT_FOUND",
            message=str(exc),
            step="GET_JOB",
            details={"job_id": job_id},
        ) from exc


@app.get("/jobs", response_model=List[JobStatusResponse])
async def list_jobs():
    """查询任务列表"""
    return await orchestrator.list_jobs()


@app.post("/jobs/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_job(job_id: str):
    """取消任务"""
    try:
        status = await orchestrator.cancel_job(job_id)
        return {
            "job_id": status["job_id"],
            "job_state": status["job_state"],
            "running_phase": status["running_phase"],
            "progress": status["progress"],
        }
    except KeyError as exc:
        raise CoreApiError(
            status_code=404,
            error_type="validation_error",
            code="VAL_JOB_NOT_FOUND",
            message=str(exc),
            step="CANCEL_JOB",
            details={"job_id": job_id},
        ) from exc


@app.get("/videos/{file_path:path}")
async def get_video(file_path: str):
    """
    提供视频文件访问

    用于前端通过 HTTP 协议播放本地生成的视频文件。
    """
    full_path = Path(file_path).expanduser().resolve()
    work_root = Path(orchestrator.work_root).resolve()

    if not full_path.is_relative_to(work_root):
        raise CoreApiError(
            status_code=403,
            error_type="validation_error",
            code="VAL_VIDEO_ACCESS_DENIED",
            message="Video path is outside work root",
            step="GET_VIDEO",
            details={"file_path": str(full_path), "work_root": str(work_root)},
        )

    if not full_path.exists():
        raise CoreApiError(
            status_code=404,
            error_type="validation_error",
            code="VAL_VIDEO_NOT_FOUND",
            message="Video file not found",
            step="GET_VIDEO",
            details={"file_path": str(full_path)},
        )

    if not full_path.is_file():
        raise CoreApiError(
            status_code=400,
            error_type="validation_error",
            code="VAL_INVALID_PATH",
            message="Path is not a file",
            step="GET_VIDEO",
            details={"file_path": str(full_path)},
        )

    return FileResponse(
        full_path,
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": "inline"
        }
    )


@app.exception_handler(CoreApiError)
async def core_api_error_handler(request: Request, exc: CoreApiError):
    """Core 业务异常处理。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            request=request,
            error_type=exc.error_type,
            code=exc.code,
            message=exc.message,
            step=exc.step,
            details=exc.details,
        ),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理。"""
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            request=request,
            error_type="runtime_error",
            code="RUN_UNHANDLED_EXCEPTION",
            message="An unexpected error occurred",
            step="UNKNOWN",
        ),
    )


# ============================================
# Main Entry Point
# ============================================

if __name__ == "__main__":
    port = int(os.getenv("CORE_PORT", 8000))
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=port,
        reload=True,
        log_level="info"
    )
