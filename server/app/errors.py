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
                "message": str(exc) or "Unhandled server error.",
                "type": "server_error",
                "details": {
                    "request_id": request_id,
                }
                if request_id
                else None,
            }
        ).model_dump(exclude_none=True),
    )

