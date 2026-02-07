"""
请求追踪中间件

实现 X-Request-ID 生成/透传和请求上下文管理
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from utils.logger import REQUEST_ID_CTX, JOB_ID_CTX, log_request, log_response, get_logger


logger = get_logger("entrocut.middleware")


# ============================================
# Request Tracking Middleware
# ============================================

class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """请求追踪中间件"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求"""
        # 生成或获取 request_id
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # 获取 job_id：优先从查询参数获取
        job_id = request.query_params.get("job_id")

        # 记录请求开始时间
        start_time = time.time()

        # 设置上下文（请求前）
        REQUEST_ID_CTX.set(request_id)
        if job_id:
            JOB_ID_CTX.set(job_id)

        # 记录请求日志
        log_request(
            method=request.method,
            path=request.url.path,
            job_id=job_id,
            request_id=request_id
        )

        # 处理请求
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            # 路由处理后，尝试从 request.state 获取 job_id
            # 路由处理函数可以将 job_id 存入 request.state.job_id
            if hasattr(request.state, "job_id") and request.state.job_id:
                job_id = request.state.job_id
                JOB_ID_CTX.set(job_id)  # 更新上下文

            # 添加 request_id 到响应头
            response.headers["X-Request-ID"] = request_id

            # 记录响应日志
            log_response(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms
            )

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # 记录错误日志
            logger.error(
                f"Request failed: {str(e)}",
                exc_info=True,
                extra={
                    "event": "error",
                    "duration_ms": duration_ms
                }
            )
            raise


# ============================================
# Helper Functions
# ============================================

def get_request_id() -> str | None:
    """获取当前请求的 request_id"""
    return REQUEST_ID_CTX.get()


def get_job_id() -> str | None:
    """获取当前请求的 job_id"""
    return JOB_ID_CTX.get()
