"""
Entrocut Server - 云端后端服务

提供用户认证、项目管理、向量检索等业务功能。
连接 MongoDB 和 DashVector。
"""

import os
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routes import auth, projects, search, mock
from models.database import connect_db, close_db
from models.schemas import HealthResponse, SERVICE_NAME, SERVICE_VERSION
from middleware.request_tracking import RequestTrackingMiddleware
from middleware.error_handler import (
    EntrocutException,
    entrocut_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    generic_exception_handler
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


# ============================================
# Configuration
# ============================================

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"


# ============================================
# Request/Response Models
# ============================================

# HealthResponse 已移至 models/schemas.py


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
    description="云端后端服务 - Mock API (MVP 阶段)",
    version=SERVICE_VERSION,
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

# 请求追踪中间件
app.add_middleware(RequestTrackingMiddleware)


# ============================================
# Exception Handlers
# ============================================

app.add_exception_handler(EntrocutException, entrocut_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


# ============================================
# Routers
# ============================================

app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["Authentication"])
app.include_router(projects.router, prefix=f"{API_PREFIX}/projects", tags=["Projects"])
app.include_router(search.router, prefix=f"{API_PREFIX}/search", tags=["Search"])
app.include_router(mock.router, prefix=f"{API_PREFIX}/mock", tags=["Mock"])


# ============================================
# Endpoints
# ============================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    健康检查

    Mock 阶段简化版，不检查数据库连接状态
    """
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
        version=SERVICE_VERSION
    )


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "docs": "/docs",
        "health": "/health",
        "mock_api": {
            "analyze": f"{API_PREFIX}/mock/analyze",
            "edl": f"{API_PREFIX}/mock/edl"
        }
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
