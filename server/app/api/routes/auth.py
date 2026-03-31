from __future__ import annotations

from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ...bootstrap.dependencies import (
    bootstrap_secret,
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
    StagingBootstrapLoginSessionRequest,
    StagingBootstrapLoginSessionResponse,
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


@router.post("/api/v1/test/bootstrap/login-session", response_model=StagingBootstrapLoginSessionResponse)
def staging_bootstrap_login_session(
    request: Request,
    payload: StagingBootstrapLoginSessionRequest,
    x_bootstrap_secret: str | None = Header(default=None),
) -> StagingBootstrapLoginSessionResponse:
    bootstrap_secret(x_bootstrap_secret)
    login_session = store.login_sessions.get(payload.login_session_id)
    if login_session is None:
        raise ServerApiError(
            status_code=404,
            code="LOGIN_SESSION_NOT_FOUND",
            message="The requested login session does not exist.",
            error_type="invalid_request_error",
        )
    unique_suffix = uuid4().hex[:12]
    profile = {
        "provider_user_id": f"{payload.provider}_staging_{unique_suffix}",
        "email": payload.email or f"staging-auth-{unique_suffix}@entrocut.local",
        "display_name": payload.display_name or f"Staging Bootstrap {unique_suffix[:6]}",
        "avatar_url": None,
    }
    user = user_service.upsert_user_from_provider(payload.provider, profile)
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
    log_event(
        logger,
        "staging_bootstrap_login_session_succeeded",
        service="server",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        login_session_id=payload.login_session_id,
        user_id=user["_id"],
        provider=payload.provider,
    )
    log_audit_event(
        "audit_staging_bootstrap_login_session_succeeded",
        env=settings.app_env,
        request_id=getattr(request.state, "request_id", None),
        actor_user_id=user["_id"],
        actor_session_id=token_bundle["session_id"],
        action="auth.test_bootstrap.login_session",
        result="success",
        target_type="login_session",
        target_id=payload.login_session_id,
        details={"provider": payload.provider},
    )
    return StagingBootstrapLoginSessionResponse(
        login_session_id=payload.login_session_id,
        status="authenticated",
        user=user_service.user_profile(user),
    )


@router.get("/api/v1/auth/dev/fallback", response_class=HTMLResponse)
def auth_dev_fallback(login_session_id: str | None = None, status: str | None = None) -> HTMLResponse:
    if not settings.auth_dev_fallback_enabled:
        raise ServerApiError(
            status_code=404,
            code="NOT_FOUND",
            message="Auth dev fallback is disabled.",
            error_type="invalid_request_error",
        )

    safe_login_session_id = login_session_id or ""
    safe_status = status or "pending"
    safe_web_url = settings.auth_dev_fallback_web_url
    html = f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>EntroCut Auth Dev Fallback</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f5f1e8;
        --panel: #fffdf9;
        --ink: #1f1b18;
        --muted: #746a60;
        --accent: #c8643b;
        --line: #dfd4c8;
      }}
      body {{
        margin: 0;
        background: radial-gradient(circle at top, #fff6df 0%, var(--bg) 55%);
        color: var(--ink);
        font-family: "Segoe UI", "PingFang SC", sans-serif;
      }}
      main {{
        max-width: 760px;
        margin: 48px auto;
        padding: 0 20px;
      }}
      .panel {{
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 24px;
        box-shadow: 0 20px 60px rgba(54, 39, 24, 0.08);
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: 28px;
      }}
      p {{
        margin: 0 0 12px;
        color: var(--muted);
        line-height: 1.6;
      }}
      code, pre {{
        font-family: "SFMono-Regular", Consolas, monospace;
      }}
      .meta {{
        margin: 18px 0;
        padding: 14px;
        border-radius: 14px;
        background: #f8f2ea;
        border: 1px solid var(--line);
      }}
      .actions {{
        display: flex;
        gap: 12px;
        margin: 18px 0;
        flex-wrap: wrap;
      }}
      button {{
        border: 0;
        border-radius: 999px;
        padding: 12px 18px;
        background: var(--accent);
        color: white;
        cursor: pointer;
        font-size: 14px;
      }}
      button.secondary {{
        background: #e7ddd2;
        color: var(--ink);
      }}
      .ok {{
        color: #0e7a44;
      }}
      .warn {{
        color: #9b5b17;
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="panel">
        <h1>EntroCut 登录已回到 Server</h1>
        <p>这是 <code>dev fallback</code> 页面，仅用于开发调试。正式桌面链路仍应优先回到 <code>entrocut://</code>。</p>
        <div class="meta">
          <div><strong>status</strong>: <span class="{ 'ok' if safe_status == 'authenticated' else 'warn' }">{safe_status}</span></div>
          <div><strong>login_session_id</strong>: <code id="session-id">{safe_login_session_id}</code></div>
        </div>
        <p>当前页面只负责开发期回落。它不会展示 token，而是自动把 <code>login_session_id</code> 回传给前端页面，再由前端自行一次性领取登录结果。</p>
        <div class="actions">
          <button id="continue-button" type="button">返回 EntroCut</button>
          <button id="copy-button" type="button" class="secondary">复制 login_session_id</button>
        </div>
        <p id="status-line">正在准备跳回 EntroCut...</p>
      </div>
    </main>
    <script>
      const loginSessionId = {safe_login_session_id!r};
      const webUrl = {safe_web_url!r};
      const statusLine = document.getElementById("status-line");
      const continueButton = document.getElementById("continue-button");
      const copyButton = document.getElementById("copy-button");

      function buildRedirectUrl() {{
        const target = new URL(webUrl);
        target.searchParams.set("auth_login_session_id", loginSessionId);
        target.searchParams.set("auth_status", "authenticated");
        return target.toString();
      }}

      function jumpBack() {{
        if (!loginSessionId) {{
          statusLine.textContent = "缺少 login_session_id";
          return;
        }}
        window.location.replace(buildRedirectUrl());
      }}

      continueButton.addEventListener("click", jumpBack);

      copyButton.addEventListener("click", async () => {{
        if (!loginSessionId) {{
          return;
        }}
        await navigator.clipboard.writeText(loginSessionId);
      }});

      window.setTimeout(jumpBack, 800);
    </script>
  </body>
</html>"""
    return HTMLResponse(content=html)


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
