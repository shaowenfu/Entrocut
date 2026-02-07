"""
结构化日志工具

输出 JSON 格式日志，支持 request_id 和 job_id 追踪
"""

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional
from contextvars import ContextVar


# ============================================
# Context Variables
# ============================================

REQUEST_ID_CTX: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
JOB_ID_CTX: ContextVar[Optional[str]] = ContextVar("job_id", default=None)


# ============================================
# JSON Formatter
# ============================================

class JSONFormatter(logging.Formatter):
    """JSON 格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为 JSON"""
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        log_data = {
            "timestamp": timestamp,
            "level": record.levelname,
            "service": "entrocut-mock-server",
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加上下文变量
        request_id = REQUEST_ID_CTX.get()
        if request_id:
            log_data["request_id"] = request_id

        job_id = JOB_ID_CTX.get()
        if job_id:
            log_data["job_id"] = job_id

        # 添加额外字段
        if hasattr(record, "event"):
            log_data["event"] = record.event
        if hasattr(record, "method"):
            log_data["method"] = record.method
        if hasattr(record, "path"):
            log_data["path"] = record.path
        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "error_code"):
            log_data["error_code"] = record.error_code
        if hasattr(record, "error_type"):
            log_data["error_type"] = record.error_type

        # 异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


# ============================================
# Logger Setup
# ============================================

def setup_logger(name: str = "entrocut", level: str = "INFO") -> logging.Logger:
    """设置结构化日志器"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除现有处理器
    logger.handlers.clear()

    # 添加 JSON 格式处理器到 stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    return logger


# ============================================
# Convenience Functions
# ============================================

def get_logger(name: str = "entrocut") -> logging.Logger:
    """获取日志器"""
    return logging.getLogger(name)


def log_request(
    method: str,
    path: str,
    job_id: Optional[str] = None,
    request_id: Optional[str] = None
):
    """记录 API 请求"""
    logger = get_logger("entrocut.api")

    # 设置上下文
    if request_id:
        REQUEST_ID_CTX.set(request_id)
    if job_id:
        JOB_ID_CTX.set(job_id)

    logger.info(
        f"{method} {path}",
        extra={"event": "api_request", "method": method, "path": path}
    )


def log_response(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float
):
    """记录 API 响应"""
    logger = get_logger("entrocut.api")

    logger.info(
        f"{method} {path} - {status_code}",
        extra={
            "event": "api_response",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms
        }
    )


def log_error(
    message: str,
    error_code: str,
    error_type: str,
    exc_info: bool = False
):
    """记录错误"""
    logger = get_logger("entrocut.api")

    logger.error(
        message,
        exc_info=exc_info,
        extra={
            "event": "error",
            "error_code": error_code,
            "error_type": error_type
        }
    )


# ============================================
# Default Logger
# ============================================

logger = setup_logger()
