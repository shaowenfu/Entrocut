"""
Entrocut Server - 云端后端服务

提供用户认证、项目管理、向量检索等业务功能。
连接 MongoDB 和 DashVector。
"""

import os
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from routes import auth, projects, search
from models.database import connect_db, close_db


# ============================================
# Configuration
# ============================================

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"


# ============================================
# Request/Response Models
# ============================================

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str
    version: str
    mongodb_connected: bool
    dashvector_connected: bool


# ============================================
# Application Lifecycle
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    print("🚀 Entrocut Server starting...")
    await connect_db()
    yield
    # 关闭时清理
    await close_db()
    print("👋 Entrocut Server shutting down...")


app = FastAPI(
    title="Entrocut Server",
    description="云端后端服务 - 用户管理与向量检索",
    version="0.1.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源，生产环境需限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Routers
# ============================================

app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["Authentication"])
app.include_router(projects.router, prefix=f"{API_PREFIX}/projects", tags=["Projects"])
app.include_router(search.router, prefix=f"{API_PREFIX}/search", tags=["Search"])


# ============================================
# Endpoints
# ============================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    from models.database import get_db_status
    db_status = await get_db_status()
    return HealthResponse(
        status="ok",
        service="entrocut-server",
        version="0.1.0",
        mongodb_connected=db_status.get("mongodb", False),
        dashvector_connected=db_status.get("dashvector", False)
    )


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "Entrocut Server",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health"
    }


# ============================================
# Main Entry Point
# ============================================

if __name__ == "__main__":
    port = int(os.getenv("SERVER_PORT", 8001))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
