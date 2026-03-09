from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RuntimeCapabilitiesResponse(BaseModel):
    service: str
    version: str
    phase: str
    mode: str
    retained_surfaces: list[str]


class LoginSessionCreateRequest(BaseModel):
    provider: Literal["google"] = "google"
    client_redirect_uri: str | None = None


class LoginSessionCreateResponse(BaseModel):
    login_session_id: str
    authorize_url: str
    expires_in: int


class UserProfile(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    status: str
    plan: str = "free"
    quota_status: str = "healthy"


class TokenBundle(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class LoginSessionResult(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"
    user: UserProfile


class LoginSessionStatusResponse(BaseModel):
    login_session_id: str
    provider: str
    status: Literal["pending", "authenticated", "failed", "consumed", "expired"]
    result: LoginSessionResult | None = None
    error: dict[str, Any] | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class RefreshTokenResponse(TokenBundle):
    pass


class MeResponse(BaseModel):
    user: UserProfile


class LogoutResponse(BaseModel):
    status: str = "ok"

