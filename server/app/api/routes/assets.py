from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from ...bootstrap.dependencies import get_current_user, logger, metrics, settings, vector_service
from ...core.errors import ServerApiError, invalid_retrieval_request, invalid_vectorize_request
from ...core.observability import log_audit_event, log_event
from ...schemas.assets import AssetRetrievalRequest, AssetRetrievalResponse, VectorizeRequest, VectorizeResponse


router = APIRouter(tags=["assets"])


@router.post("/v1/assets/vectorize", response_model=VectorizeResponse)
async def vectorize_asset(
    request: Request,
    current: dict = Depends(get_current_user),
) -> VectorizeResponse:
    try:
        raw_payload = await request.json()
    except json.JSONDecodeError as exc:
        raise invalid_vectorize_request("Request body must be valid JSON.") from exc
    try:
        payload = VectorizeRequest.model_validate(raw_payload)
    except ValidationError as exc:
        raise invalid_vectorize_request(
            "Vectorize request validation failed.",
            details={"validation_errors": exc.errors()},
        ) from exc
    try:
        log_event(
            logger,
            "vectorize_started",
            service="server",
            env=settings.app_env,
            request_id=getattr(request.state, "request_id", None),
            user_id=current["user"]["_id"],
            collection_name=payload.collection_name,
            doc_count=len(payload.docs),
        )
        result = vector_service.vectorize(payload)
        metrics.inc("server_vectorize_requests_total", status="success")
        log_event(
            logger,
            "vectorize_succeeded",
            service="server",
            env=settings.app_env,
            request_id=getattr(request.state, "request_id", None),
            user_id=current["user"]["_id"],
            collection_name=payload.collection_name,
            inserted_count=result["inserted_count"],
            dimension=result["dimension"],
        )
        log_audit_event(
            "audit_vectorize_succeeded",
            env=settings.app_env,
            request_id=getattr(request.state, "request_id", None),
            actor_user_id=current["user"]["_id"],
            action="assets.vectorize",
            result="success",
            target_type="collection",
            target_id=payload.collection_name,
            details={"dimension": result["dimension"], "inserted_count": result["inserted_count"]},
        )
        return VectorizeResponse(**result)
    except ServerApiError:
        metrics.inc("server_vectorize_requests_total", status="error")
        raise
    except Exception as exc:
        raise ServerApiError(
            status_code=500,
            code="VECTORIZE_WRITE_FAILED",
            message=f"Vectorization failed: {exc}",
            error_type="server_error",
        ) from exc


@router.post("/v1/assets/retrieval", response_model=AssetRetrievalResponse)
async def assets_retrieval(
    request: Request,
    current: dict = Depends(get_current_user),
) -> AssetRetrievalResponse:
    try:
        raw_payload = await request.json()
    except json.JSONDecodeError as exc:
        raise invalid_retrieval_request("Request body must be valid JSON.") from exc
    try:
        payload = AssetRetrievalRequest.model_validate(raw_payload)
    except ValidationError as exc:
        raise invalid_retrieval_request(
            "Retrieval request validation failed.",
            details={"validation_errors": exc.errors()},
        ) from exc
    log_event(
        logger,
        "retrieval_started",
        service="server",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        user_id=current["user"]["_id"],
        collection_name=payload.collection_name,
        topk=payload.topk,
    )
    result = vector_service.retrieve(payload)
    metrics.inc("server_vector_retrieval_requests_total", status="success")
    log_event(
        logger,
        "retrieval_succeeded",
        service="server",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        user_id=current["user"]["_id"],
        collection_name=payload.collection_name,
        match_count=len(result.get("matches", [])),
    )
    log_audit_event(
        "audit_retrieval_succeeded",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        actor_user_id=current["user"]["_id"],
        action="assets.retrieval",
        result="success",
        target_type="collection",
        target_id=payload.collection_name,
        details={"match_count": len(result.get("matches", [])), "topk": payload.topk},
    )
    return AssetRetrievalResponse(**result)
