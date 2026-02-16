"""
向量检索相关路由

使用 DashVector 进行语义搜索。

Round 4: 向量检索功能未实现，返回 501 Not Implemented
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from middleware.error_handler import NotImplementedException

router = APIRouter()


# ============================================
# Models
# ============================================

class SearchResult(BaseModel):
    """搜索结果"""
    frame_id: str
    video_id: str
    timestamp: float
    similarity: float
    thumbnail_url: Optional[str] = None


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str
    project_id: Optional[str] = None
    top_k: int = 10


class SearchResponse(BaseModel):
    """搜索响应"""
    query: str
    results: List[SearchResult]
    total: int


# ============================================
# Endpoints
# ============================================

@router.post("", response_model=SearchResponse)
async def semantic_search(request: SearchRequest):
    """
    语义搜索

    Round 4: 向量检索功能未实现，返回 501
    计划在 Round 5+ 实现 DashScope + DashVector 集成
    """
    raise NotImplementedException("Vector Search: Semantic Search")


@router.get("/similar/{frame_id}")
async def find_similar_frames(frame_id: str, top_k: int = 10):
    """
    查找相似帧

    Round 4: 向量检索功能未实现，返回 501
    计划在 Round 5+ 实现 DashVector 集成
    """
    raise NotImplementedException("Vector Search: Find Similar Frames")
