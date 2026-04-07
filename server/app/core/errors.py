from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]


class ServerApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        error_type: str = "server_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.error_type = error_type
        self.details = details or {}


def error_payload(error: ServerApiError, request_id: str | None) -> dict[str, Any]:
    details = dict(error.details)
    if request_id:
        details.setdefault("request_id", request_id)
    return ErrorEnvelope(
        error={
            "code": error.code,
            "message": error.message,
            "type": error.error_type,
            "details": details or None,
            "request_id": request_id,
        }
    ).model_dump(exclude_none=True)


async def server_api_error_handler(request: Request, exc: ServerApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc, getattr(request.state, "request_id", None)),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content=ErrorEnvelope(
            error={
                "code": "SERVER_INTERNAL_ERROR",
                "message": "Unhandled server error.",
                "type": "server_error",
                "details": {
                    "request_id": request_id,
                }
                if request_id
                else None,
            }
        ).model_dump(exclude_none=True),
    )


# ============ Vector Error Factories ============


def vectorize_error(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    """向量化处理错误"""
    return ServerApiError(
        status_code=422,
        code="VECTORIZE_ERROR",
        message=message,
        error_type="invalid_request_error",
        details=details,
    )


def invalid_vectorize_request(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=422,
        code="INVALID_VECTORIZE_REQUEST",
        message=message,
        error_type="invalid_request_error",
        details=details,
    )


def image_decode_failed(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=422,
        code="IMAGE_DECODE_FAILED",
        message=message,
        error_type="invalid_request_error",
        details=details,
    )


def embedding_provider_unavailable(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=502,
        code="EMBEDDING_PROVIDER_UNAVAILABLE",
        message=message,
        error_type="server_error",
        details=details,
    )


def vector_store_unavailable(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=502,
        code="VECTOR_STORE_UNAVAILABLE",
        message=message,
        error_type="server_error",
        details=details,
    )


def vectorize_write_failed(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=502,
        code="VECTORIZE_WRITE_FAILED",
        message=message,
        error_type="server_error",
        details=details,
    )


def invalid_retrieval_request(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=422,
        code="INVALID_RETRIEVAL_REQUEST",
        message=message,
        error_type="invalid_request_error",
        details=details,
    )


def query_embedding_failed(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=502,
        code="QUERY_EMBEDDING_FAILED",
        message=message,
        error_type="server_error",
        details=details,
    )


def retrieval_failed(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=502,
        code="RETRIEVAL_FAILED",
        message=message,
        error_type="server_error",
        details=details,
    )


def vector_embedding_error(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    """Embedding API 调用失败"""
    return ServerApiError(
        status_code=502,
        code="VECTOR_EMBEDDING_ERROR",
        message=message,
        error_type="server_error",
        details=details,
    )


def vector_db_error(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    """向量数据库操作失败"""
    return ServerApiError(
        status_code=502,
        code="VECTOR_DB_ERROR",
        message=message,
        error_type="server_error",
        details=details,
    )


def vector_config_error(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    """向量服务配置错误"""
    return ServerApiError(
        status_code=503,
        code="VECTOR_CONFIG_ERROR",
        message=message,
        error_type="server_error",
        details=details,
    )


# ============ Inspect Error Factories ============


def invalid_inspect_request(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=422,
        code="INVALID_INSPECT_REQUEST",
        message=message,
        error_type="invalid_request_error",
        details=details,
    )


def inspect_evidence_missing(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=422,
        code="INSPECT_EVIDENCE_MISSING",
        message=message,
        error_type="invalid_request_error",
        details=details,
    )


def inspect_provider_unavailable(
    message: str,
    *,
    status_code: int = 503,
    details: dict[str, Any] | None = None,
) -> ServerApiError:
    return ServerApiError(
        status_code=status_code,
        code="INSPECT_PROVIDER_UNAVAILABLE",
        message=message,
        error_type="server_error",
        details=details,
    )


def inspect_provider_invalid_response(
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> ServerApiError:
    return ServerApiError(
        status_code=502,
        code="INSPECT_PROVIDER_INVALID_RESPONSE",
        message=message,
        error_type="server_error",
        details=details,
    )


def decision_inconclusive(message: str, *, details: dict[str, Any] | None = None) -> ServerApiError:
    return ServerApiError(
        status_code=409,
        code="DECISION_INCONCLUSIVE",
        message=message,
        error_type="server_error",
        details=details,
    )
