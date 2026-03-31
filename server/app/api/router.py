from __future__ import annotations

from fastapi import APIRouter

from .routes import assets_router, auth_router, build_user_router, chat_router, health_router, inspect_router, runtime_router
from ..bootstrap.dependencies import get_current_user, user_service


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(runtime_router)
api_router.include_router(auth_router)
api_router.include_router(chat_router)
api_router.include_router(assets_router)
api_router.include_router(inspect_router)
api_router.include_router(
    build_user_router(get_current_user_dependency=get_current_user, user_service=user_service)
)
