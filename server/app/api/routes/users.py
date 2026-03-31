from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends

from ...schemas.user import UserProfileResponse, UserUsageResponse, UserUsageSnapshot
from ...services.auth.users import UserService


def build_user_router(
    *,
    get_current_user_dependency: Callable[..., dict[str, Any]],
    user_service: UserService,
) -> APIRouter:
    router = APIRouter(tags=["user"])

    @router.get("/user/profile", response_model=UserProfileResponse)
    def get_user_profile(
        current: dict[str, Any] = Depends(get_current_user_dependency),
    ) -> UserProfileResponse:
        return UserProfileResponse(user=user_service.user_profile(current["user"]))

    @router.get("/user/usage", response_model=UserUsageResponse)
    def get_user_usage(
        current: dict[str, Any] = Depends(get_current_user_dependency),
    ) -> UserUsageResponse:
        return UserUsageResponse(
            user_id=current["user"]["_id"],
            usage=UserUsageSnapshot.model_validate(user_service.usage_snapshot(current["user"])),
        )

    return router
