"""
Entrocut Core - 本地算法 Sidecar 服务

提供视频处理、场景检测、抽帧等功能的核心算法服务。
运行在本地，与 Electron 主进程通信。
"""

import os
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from detect.scene_detector import SceneDetector
from process.frame_extractor import FrameExtractor


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


# ============================================
# Endpoints
# ============================================

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
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Video file not found: {request.video_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scene detection failed: {str(e)}")


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
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Video file not found: {request.video_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Frame extraction failed: {str(e)}")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
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
