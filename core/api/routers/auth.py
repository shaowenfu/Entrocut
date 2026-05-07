from fastapi import APIRouter

from application.store import auth_session_store
from contracts import CoreAuthSessionRequest, CoreAuthSessionResponse

router = APIRouter()


@router.post("/api/v1/auth/session", response_model=CoreAuthSessionResponse)
async def set_auth_session(payload: CoreAuthSessionRequest) -> CoreAuthSessionResponse:
    await auth_session_store.set_session(payload.access_token, payload.user_id)
    return CoreAuthSessionResponse(user_id=payload.user_id)


@router.delete("/api/v1/auth/session", response_model=CoreAuthSessionResponse)
async def clear_auth_session() -> CoreAuthSessionResponse:
    await auth_session_store.clear_session()
    return CoreAuthSessionResponse(user_id=None)
