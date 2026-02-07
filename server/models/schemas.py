"""
Mock API 请求/响应 Schema

根据 T1 最小契约定义（contract_version: 0.1.0-mock）
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone


# ============================================
# Common Models
# ============================================

class ErrorDetail(BaseModel):
    """错误详情"""
    field: Optional[str] = None
    expected: Optional[str] = None
    received: Optional[str] = None


class ErrorResponse(BaseModel):
    """统一错误响应"""
    error: dict = Field(..., description="错误对象")


# ============================================
# Mock Analyze API
# ============================================

class FrameInfo(BaseModel):
    """帧信息"""
    timestamp: float = Field(..., description="帧时间戳（秒）")
    frame_number: Optional[int] = Field(None, description="帧序号")
    file_path: str = Field(..., description="帧文件绝对路径")


class AnalyzeRequest(BaseModel):
    """Mock 分析请求"""
    job_id: str = Field(..., description="任务编号（UUID）")
    contract_version: str = Field(..., description="契约版本")
    video_path: str = Field(..., description="视频文件绝对路径")
    frames: List[FrameInfo] = Field(..., description="关键帧列表")


class SegmentInfo(BaseModel):
    """片段信息"""
    segment_id: str = Field(..., description="片段编号")
    start_time: float = Field(..., description="开始时间（秒）")
    end_time: float = Field(..., description="结束时间（秒）")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    score: float = Field(default=0.0, description="置信度分数")
    description: Optional[str] = Field(None, description="描述信息")


class AnalysisData(BaseModel):
    """分析结果数据"""
    segments: List[SegmentInfo] = Field(default_factory=list, description="片段列表")


class AnalyzeResponse(BaseModel):
    """Mock 分析响应"""
    contract_version: str = Field(..., description="契约版本")
    job_id: str = Field(..., description="任务编号")
    request_id: str = Field(..., description="请求编号")
    analysis: AnalysisData = Field(..., description="分析结果")


# ============================================
# Mock EDL API
# ============================================

class SegmentRef(BaseModel):
    """片段引用（用于 EDL 请求）"""
    segment_id: str = Field(..., description="片段编号")
    start_time: float = Field(..., description="开始时间（秒）")
    end_time: float = Field(..., description="结束时间（秒）")


class EDLRequest(BaseModel):
    """Mock EDL 请求"""
    job_id: str = Field(..., description="任务编号（UUID）")
    contract_version: str = Field(..., description="契约版本")
    video_path: Optional[str] = Field(None, description="视频文件绝对路径（用于生成真实 src）")
    segments: List[SegmentRef] = Field(..., description="片段列表")
    rule: str = Field(default="highlight_first", description="剪辑规则")


class ClipInfo(BaseModel):
    """剪辑片段信息"""
    clip_id: str = Field(..., description="片段编号")
    src: str = Field(..., description="源视频文件路径")
    start: float = Field(..., description="开始时间（秒）")
    end: float = Field(..., description="结束时间（秒）")


class EDLData(BaseModel):
    """EDL 数据"""
    clips: List[ClipInfo] = Field(default_factory=list, description="剪辑片段列表")
    output_name: str = Field(..., description="输出文件名")
    total_duration: float = Field(..., description="总时长（秒）")


class EDLResponse(BaseModel):
    """Mock EDL 响应"""
    contract_version: str = Field(..., description="契约版本")
    job_id: str = Field(..., description="任务编号")
    request_id: str = Field(..., description="请求编号")
    edl: EDLData = Field(..., description="EDL 数据")


# ============================================
# Health Check
# ============================================

class HealthResponse(BaseModel):
    """健康检查响应（Mock 阶段简化版）"""
    status: str = Field(..., description="服务状态")
    service: str = Field(..., description="服务名称")
    version: str = Field(..., description="服务版本")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="时间戳")


# ============================================
# Constants
# ============================================

CONTRACT_VERSION = "0.1.0-mock"
SERVICE_NAME = "entrocut-mock-server"
SERVICE_VERSION = "0.1.0-mock"
