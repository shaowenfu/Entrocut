from __future__ import annotations

from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from ...bootstrap.dependencies import (
    get_current_user,
    logger,
    oauth_service,
    settings,
    store,
    token_service,
    user_service,
)
from ...core.errors import ServerApiError
from ...core.observability import log_audit_event, log_event
from ...schemas.auth import (
    LoginSessionCreateRequest,
    LoginSessionCreateResponse,
    LoginSessionResult,
    LoginSessionStatusResponse,
    LogoutResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from ...schemas.user import MeResponse


router = APIRouter(tags=["auth"])


@router.post("/api/v1/auth/login-sessions", response_model=LoginSessionCreateResponse)
def create_login_session(request: Request, payload: LoginSessionCreateRequest) -> LoginSessionCreateResponse:
    login_session = oauth_service.create_login_session(payload.provider, payload.client_redirect_uri)
    authorize_url = (
        f"{settings.server_base_url.rstrip('/')}/api/v1/auth/oauth/{payload.provider}/start?"
        + urlencode({"login_session_id": login_session["login_session_id"]})
    )
    log_event(
        logger,
        "auth_login_session_created",
        service="server",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        login_session_id=login_session["login_session_id"],
        provider=payload.provider,
    )
    log_audit_event(
        "audit_login_session_created",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        action="auth.login_session.create",
        result="success",
        target_type="login_session",
        target_id=login_session["login_session_id"],
        details={"provider": payload.provider},
    )
    return LoginSessionCreateResponse(
        login_session_id=login_session["login_session_id"],
        authorize_url=authorize_url,
        expires_in=settings.auth_login_session_ttl_seconds,
    )


@router.get("/api/v1/auth/oauth/{provider}/start")
def start_oauth(request: Request, provider: str, login_session_id: str) -> RedirectResponse:
    authorize_url = oauth_service.create_authorize_url(provider, login_session_id)
    log_event(
        logger,
        "auth_oauth_started",
        service="server",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        login_session_id=login_session_id,
        provider=provider,
    )
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/api/v1/auth/oauth/{provider}/callback")
async def oauth_callback(provider: str, request: Request) -> RedirectResponse:
    callback_data = await oauth_service.handle_callback(provider, str(request.url))
    login_session = callback_data["login_session"]
    user = user_service.upsert_user_from_provider(provider, callback_data["profile"])
    token_bundle = token_service.issue_session_bundle(user)
    login_session["status"] = "authenticated"
    login_session["result"] = {
        "access_token": token_bundle["access_token"],
        "refresh_token": token_bundle["refresh_token"],
        "expires_in": token_bundle["expires_in"],
        "token_type": token_bundle["token_type"],
        "user": user_service.user_profile(user),
    }
    login_session["error"] = None
    store.login_sessions.save(login_session)
    redirect_uri = login_session["client_redirect_uri"] or settings.default_client_redirect_uri
    redirect_query = urlencode(
        {
            "auth_login_session_id": login_session["login_session_id"],
            "auth_status": "authenticated",
        }
    )
    separator = "&" if "?" in redirect_uri else "?"
    log_event(
        logger,
        "auth_oauth_callback_succeeded",
        service="server",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        login_session_id=login_session["login_session_id"],
        provider=provider,
        user_id=user["_id"],
        session_id=token_bundle["session_id"],
    )
    log_audit_event(
        "audit_oauth_callback_succeeded",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        actor_user_id=user["_id"],
        actor_session_id=token_bundle["session_id"],
        action="auth.oauth.callback",
        result="success",
        target_type="login_session",
        target_id=login_session["login_session_id"],
        details={"provider": provider},
    )
    return RedirectResponse(url=f"{redirect_uri}{separator}{redirect_query}", status_code=302)


@router.get("/api/v1/auth/login-sessions/{login_session_id}", response_model=LoginSessionStatusResponse)
def get_login_session(request: Request, login_session_id: str) -> LoginSessionStatusResponse:
    login_session, claimed_result = store.login_sessions.consume_once(login_session_id)
    if login_session is None:
        raise ServerApiError(
            status_code=404,
            code="LOGIN_SESSION_NOT_FOUND",
            message="The requested login session does not exist.",
            error_type="invalid_request_error",
        )
    result = claimed_result or login_session.get("result")
    log_event(
        logger,
        "auth_login_session_claimed",
        service="server",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        login_session_id=login_session_id,
        status=login_session["status"],
        consumed=claimed_result is not None,
    )
    log_audit_event(
        "audit_login_session_claimed",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        action="auth.login_session.claim",
        result="success" if claimed_result is not None else "noop",
        target_type="login_session",
        target_id=login_session_id,
        details={"status": login_session["status"]},
    )
    return LoginSessionStatusResponse(
        login_session_id=login_session["login_session_id"],
        provider=login_session["provider"],
        status=login_session["status"],
        result=LoginSessionResult.model_validate(result) if result else None,
        error=login_session.get("error"),
    )


@router.post("/api/v1/auth/refresh", response_model=RefreshTokenResponse)
def refresh_token(request: Request, payload: RefreshTokenRequest) -> RefreshTokenResponse:
    bundle = token_service.refresh_access_token(payload.refresh_token)
    log_event(
        logger,
        "auth_refresh_succeeded",
        service="server",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        session_id=bundle["session_id"],
    )
    log_audit_event(
        "audit_refresh_succeeded",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        actor_session_id=bundle["session_id"],
        action="auth.refresh",
        result="success",
        target_type="session",
        target_id=bundle["session_id"],
    )
    return RefreshTokenResponse(
        access_token=bundle["access_token"],
        refresh_token=bundle["refresh_token"],
        expires_in=bundle["expires_in"],
        token_type=bundle["token_type"],
    )


@router.post("/api/v1/auth/logout", response_model=LogoutResponse)
def logout(request: Request, current: dict = Depends(get_current_user)) -> LogoutResponse:
    token_service.logout(current["token_payload"]["sid"])
    log_event(
        logger,
        "auth_logout_succeeded",
        service="server",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        user_id=current["user"]["_id"],
        session_id=current["token_payload"]["sid"],
    )
    log_audit_event(
        "audit_logout_succeeded",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        actor_user_id=current["user"]["_id"],
        actor_session_id=current["token_payload"]["sid"],
        action="auth.logout",
        result="success",
        target_type="session",
        target_id=current["token_payload"]["sid"],
    )
    return LogoutResponse()


@router.get("/api/v1/me", response_model=MeResponse)
def get_me(current: dict = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=user_service.user_profile(current["user"]))
