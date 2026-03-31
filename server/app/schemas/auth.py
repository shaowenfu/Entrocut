from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .user import UserProfile


class LoginSessionCreateRequest(BaseModel):
    provider: Literal["google", "github"] = "google"
    client_redirect_uri: str | None = None


class LoginSessionCreateResponse(BaseModel):
    login_session_id: str
    authorize_url: str
    expires_in: int


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


class StagingBootstrapLoginSessionRequest(BaseModel):
    login_session_id: str = Field(min_length=8)
    provider: Literal["google", "github"] = "google"
    email: str | None = None
    display_name: str | None = None


class StagingBootstrapLoginSessionResponse(BaseModel):
    login_session_id: str
    status: Literal["authenticated"]
    user: UserProfile


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class RefreshTokenResponse(TokenBundle):
    pass


class LogoutResponse(BaseModel):
    status: str = "ok"
