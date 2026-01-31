"""
向量检索相关路由

使用 DashVector 进行语义搜索。
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

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

    使用 DashScope 将 query 转为向量，然后在 DashVector 中检索。

    TODO:
    1. 调用 DashScope API 获取 query 的向量表示
    2. 在 DashVector 中进行相似度搜索
    3. 返回匹配的帧
    """
    # 临时实现
    return SearchResponse(
        query=request.query,
        results=[],
        total=0
    )


@router.get("/similar/{frame_id}")
async def find_similar_frames(frame_id: str, top_k: int = 10):
    """
    查找相似帧

    基于给定的帧 ID，查找视觉上相似的帧。

    TODO: 使用 DashVector 的向量搜索
    """
    return {
        "frame_id": frame_id,
        "similar_frames": []
    }
