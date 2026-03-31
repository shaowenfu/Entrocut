from __future__ import annotations

from pydantic import BaseModel


class UserProfile(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    status: str
    credits_balance: int = 0


class MeResponse(BaseModel):
    user: UserProfile


class UserProfileResponse(BaseModel):
    user: UserProfile


class UserUsageSnapshot(BaseModel):
    credits_balance: int = 0
    consumed_tokens_today: int = 0
    consumed_tokens_this_month: int = 0
    request_count_today: int = 0
    request_count_this_month: int = 0
    subscription_status: str = "active"
    rate_limit_requests_per_minute: int
    rate_limit_tokens_per_minute: int


class UserUsageResponse(BaseModel):
    user_id: str
    usage: UserUsageSnapshot
