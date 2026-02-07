"""
Mock API 路由

提供 Mock 分析和 EDL 接口（contract_version: 0.1.0-mock）
"""

from fastapi import APIRouter, Request
from models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnalysisData,
    EDLRequest,
    EDLResponse,
    CONTRACT_VERSION
)
from utils.mock_data import generate_mock_analysis, generate_mock_edl
from utils.logger import get_request_id, get_logger
from middleware.error_handler import (
    ValidationException,
    ErrorCode,
    ErrorType
)


router = APIRouter()
logger = get_logger("entrocat.api.mock")


# ============================================
# Constants
# ============================================

SUPPORTED_CONTRACT_VERSIONS = ["0.1.0-mock", "0.1.0"]


# ============================================
# Helper Functions
# ============================================

def validate_contract_version(contract_version: str) -> None:
    """验证契约版本"""
    if contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        raise ValidationException(
            message=f"Unsupported contract version: {contract_version}. Supported: {SUPPORTED_CONTRACT_VERSIONS}",
            code=ErrorCode.VAL_CONTRACT_VERSION_MISMATCH,
            details={
                "provided": contract_version,
                "supported": SUPPORTED_CONTRACT_VERSIONS
            }
        )


def validate_frames(frames: list) -> None:
    """验证帧列表"""
    if not frames:
        raise ValidationException(
            message="Frames list cannot be empty",
            code=ErrorCode.VAL_EMPTY_INPUT,
            details={"field": "frames"}
        )


def validate_segments(segments: list) -> None:
    """验证片段列表"""
    if not segments:
        raise ValidationException(
            message="Segments list cannot be empty",
            code=ErrorCode.VAL_EMPTY_INPUT,
            details={"field": "segments"}
        )


# ============================================
# Endpoints
# ============================================

@router.post("/analyze", response_model=AnalyzeResponse)
async def mock_analyze(request: Request, body: AnalyzeRequest) -> AnalyzeResponse:
    """
    Mock 分析接口

    接收帧元数据，返回结构化分析结果。

    Args:
        request: FastAPI 请求对象
        body: 分析请求

    Returns:
        AnalyzeResponse: 分析响应
    """
    request_id = get_request_id()

    logger.info(
        f"Mock analyze request for job: {body.job_id}",
        extra={"job_id": body.job_id, "event": "mock_analyze"}
    )

    # 验证契约版本
    validate_contract_version(body.contract_version)

    # 验证帧列表
    validate_frames(body.frames)

    # 生成 Mock 分析数据
    analysis_data = generate_mock_analysis(
        job_id=body.job_id,
        video_path=body.video_path,
        frames_count=len(body.frames)
    )

    return AnalyzeResponse(
        contract_version=CONTRACT_VERSION,
        job_id=body.job_id,
        request_id=request_id or "unknown",
        analysis=analysis_data
    )


@router.post("/edl", response_model=EDLResponse)
async def mock_edl(request: Request, body: EDLRequest) -> EDLResponse:
    """
    Mock EDL 接口

    接收分析结果，返回剪辑片段列表。

    Args:
        request: FastAPI 请求对象
        body: EDL 请求

    Returns:
        EDLResponse: EDL 响应
    """
    request_id = get_request_id()

    logger.info(
        f"Mock EDL request for job: {body.job_id}, rule: {body.rule}",
        extra={"job_id": body.job_id, "event": "mock_edl"}
    )

    # 验证契约版本
    validate_contract_version(body.contract_version)

    # 验证片段列表
    validate_segments(body.segments)

    # 生成 Mock EDL 数据
    # 需要从 segments 中获取视频路径，这里使用第一个片段的信息
    video_path = f"/local/path/to/{body.job_id}.mp4"  # Mock 路径

    edl_data = generate_mock_edl(
        job_id=body.job_id,
        segments=body.segments,
        video_path=video_path,
        rule=body.rule
    )

    return EDLResponse(
        contract_version=CONTRACT_VERSION,
        job_id=body.job_id,
        request_id=request_id or "unknown",
        edl=edl_data
    )
