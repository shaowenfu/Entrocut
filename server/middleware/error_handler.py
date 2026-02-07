"""
统一错误处理中间件

实现 validation_error/runtime_error/external_error 三类错误的统一处理
"""

from datetime import datetime
from typing import Any, Dict
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from utils.logger import log_error
from middleware.request_tracking import get_request_id


# ============================================
# Error Types
# ============================================

class ErrorType:
    """错误类型"""
    VALIDATION = "validation_error"
    RUNTIME = "runtime_error"
    EXTERNAL = "external_error"


# ============================================
# Error Codes
# ============================================

class ErrorCode:
    """错误码定义"""

    # validation_error (400)
    VAL_VIDEO_NOT_FOUND = "VAL_VIDEO_NOT_FOUND"
    VAL_VIDEO_FORMAT_UNSUPPORTED = "VAL_VIDEO_FORMAT_UNSUPPORTED"
    VAL_EMPTY_INPUT = "VAL_EMPTY_INPUT"
    VAL_MISSING_REQUIRED_FIELD = "VAL_MISSING_REQUIRED_FIELD"
    VAL_CONTRACT_VERSION_MISMATCH = "VAL_CONTRACT_VERSION_MISMATCH"
    VAL_INVALID_FIELD_FORMAT = "VAL_INVALID_FIELD_FORMAT"

    # runtime_error (500)
    RUN_SCENE_DETECT_FAILED = "RUN_SCENE_DETECT_FAILED"
    RUN_FRAME_EXTRACT_FAILED = "RUN_FRAME_EXTRACT_FAILED"
    RUN_RENDER_FAILED = "RUN_RENDER_FAILED"
    RUN_CANCELLED_BY_USER = "RUN_CANCELLED_BY_USER"
    RUN_MOCK_DATA_GENERATION_FAILED = "RUN_MOCK_DATA_GENERATION_FAILED"
    RUN_UNHANDLED_EXCEPTION = "RUN_UNHANDLED_EXCEPTION"

    # external_error (502/503)
    EXT_MOCK_TIMEOUT = "EXT_MOCK_TIMEOUT"
    EXT_MOCK_UNAVAILABLE = "EXT_MOCK_UNAVAILABLE"
    EXT_MOCK_BAD_RESPONSE = "EXT_MOCK_BAD_RESPONSE"
    EXT_UPSTREAM_UNAVAILABLE = "EXT_UPSTREAM_UNAVAILABLE"


# ============================================
# Custom Exceptions
# ============================================

class EntrocutException(Exception):
    """Entrocut 基础异常"""

    def __init__(
        self,
        message: str,
        code: str,
        error_type: str = ErrorType.RUNTIME,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Dict[str, Any] = None
    ):
        self.message = message
        self.code = code
        self.error_type = error_type
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ValidationException(EntrocutException):
    """验证异常"""

    def __init__(self, message: str, code: str = ErrorCode.VAL_MISSING_REQUIRED_FIELD, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            code=code,
            error_type=ErrorType.VALIDATION,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class RuntimeException(EntrocutException):
    """运行时异常"""

    def __init__(self, message: str, code: str = ErrorCode.RUN_UNHANDLED_EXCEPTION, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            code=code,
            error_type=ErrorType.RUNTIME,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class ExternalException(EntrocutException):
    """外部服务异常"""

    def __init__(self, message: str, code: str = ErrorCode.EXT_MOCK_UNAVAILABLE, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            code=code,
            error_type=ErrorType.EXTERNAL,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details
        )


# ============================================
# Error Response Builder
# ============================================

def build_error_response(
    error_type: str,
    code: str,
    message: str,
    details: Dict[str, Any] = None
) -> Dict[str, Any]:
    """构建错误响应"""
    return {
        "error": {
            "type": error_type,
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": get_request_id(),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    }


# ============================================
# Exception Handlers
# ============================================

async def entrocut_exception_handler(request: Request, exc: EntrocutException) -> JSONResponse:
    """Entrocut 异常处理器"""
    log_error(
        message=exc.message,
        error_code=exc.code,
        error_type=exc.error_type,
        exc_info=False
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_response(
            error_type=exc.error_type,
            code=exc.code,
            message=exc.message,
            details=exc.details
        )
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Pydantic 验证异常处理器"""
    errors = exc.errors()
    details = {}

    for error in errors:
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        details[field] = {
            "expected": error.get("type", "unknown"),
            "received": error.get("input", "unknown")
        }

    log_error(
        message=f"Validation failed: {errors[0]['msg'] if errors else 'Unknown error'}",
        error_code=ErrorCode.VAL_INVALID_FIELD_FORMAT,
        error_type=ErrorType.VALIDATION,
        exc_info=False
    )

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=build_error_response(
            error_type=ErrorType.VALIDATION,
            code=ErrorCode.VAL_INVALID_FIELD_FORMAT,
            message=f"Request validation failed: {errors[0]['msg'] if errors else 'Unknown error'}",
            details=details
        )
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """HTTP 异常处理器"""
    error_type = ErrorType.RUNTIME if 500 <= exc.status_code < 600 else ErrorType.VALIDATION

    log_error(
        message=exc.detail,
        error_code=f"HTTP_{exc.status_code}",
        error_type=error_type,
        exc_info=False
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_response(
            error_type=error_type,
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail)
        )
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """通用异常处理器"""
    log_error(
        message=f"Unhandled exception: {str(exc)}",
        error_code=ErrorCode.RUN_UNHANDLED_EXCEPTION,
        error_type=ErrorType.RUNTIME,
        exc_info=True
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=build_error_response(
            error_type=ErrorType.RUNTIME,
            code=ErrorCode.RUN_UNHANDLED_EXCEPTION,
            message="An unexpected error occurred"
        )
    )
