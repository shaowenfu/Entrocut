"""
项目管理相关路由

创建项目、查询项目列表、更新项目等。

Round 4: 项目管理功能未实现，返回 501 Not Implemented
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from middleware.error_handler import NotImplementedException

router = APIRouter()


# ============================================
# Models
# ============================================

class ProjectCreate(BaseModel):
    """创建项目请求"""
    name: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    """项目响应"""
    id: str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    video_count: int = 0


class ProjectListResponse(BaseModel):
    """项目列表响应"""
    projects: List[ProjectResponse]
    total: int


# ============================================
# Endpoints
# ============================================

@router.get("", response_model=ProjectListResponse)
async def list_projects(skip: int = 0, limit: int = 20):
    """
    获取用户的项目列表

    Round 4: 项目管理功能未实现，返回 501
    计划在 Round 5+ 实现 MongoDB 集成
    """
    raise NotImplementedException("Project Management: List Projects")


@router.post("", response_model=ProjectResponse)
async def create_project(request: ProjectCreate):
    """
    创建新项目

    Round 4: 项目管理功能未实现，返回 501
    计划在 Round 5+ 实现 MongoDB 集成
    """
    raise NotImplementedException("Project Management: Create Project")


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    """
    获取项目详情

    Round 4: 项目管理功能未实现，返回 501
    计划在 Round 5+ 实现 MongoDB 集成
    """
    raise NotImplementedException("Project Management: Get Project")


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """
    删除项目

    Round 4: 项目管理功能未实现，返回 501
    计划在 Round 5+ 实现 MongoDB 集成
    """
    raise NotImplementedException("Project Management: Delete Project")
