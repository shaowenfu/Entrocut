from __future__ import annotations

from contextlib import asynccontextmanager
import json
import time
from datetime import timezone
from typing import Any
from uuid import uuid4
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from .auth_service import OAuthService, TokenService, UserService
from .auth_store import AuthStore, now_utc
from .config import Settings, get_settings
from .errors import (
    ServerApiError,
    server_api_error_handler,
    unhandled_error_handler,
)
from .models import (
    LoginSessionCreateRequest,
    LoginSessionCreateResponse,
    LoginSessionResult,
    LoginSessionStatusResponse,
    LogoutResponse,
    MeResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RuntimeCapabilitiesResponse,
)


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


settings = get_settings()
store = AuthStore(settings)
oauth_service = OAuthService(settings, store)
user_service = UserService(store)
token_service = TokenService(settings, store)


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.ensure_indexes()
    yield


app = FastAPI(title="EntroCut Server", version=settings.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[*settings.allow_origins, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(ServerApiError, server_api_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "").strip() or _request_id()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise ServerApiError(
            status_code=401,
            code="AUTH_TOKEN_MISSING",
            message="Authorization header is required.",
            error_type="auth_error",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ServerApiError(
            status_code=401,
            code="AUTH_TOKEN_INVALID",
            message="Authorization header must be a Bearer token.",
            error_type="auth_error",
        )
    return token.strip()


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    payload = token_service.decode_access_token(_bearer_token(authorization))
    user = store.mongo.find_user_by_id(payload["sub"])
    if user is None:
        raise ServerApiError(
            status_code=401,
            code="AUTH_TOKEN_INVALID",
            message="The current user no longer exists.",
            error_type="auth_error",
        )
    if user.get("status") != "active":
        raise ServerApiError(
            status_code=403,
            code="USER_SUSPENDED",
            message="The current user is suspended.",
            error_type="auth_error",
        )
    return {"user": user, "token_payload": payload}


def _extract_message_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = [
                part.get("text", "").strip()
                for part in content
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
            ]
            if parts:
                return " ".join(part for part in parts if part)
    return ""


def _resolve_upstream_model(model: str) -> str:
    if settings.llm_upstream_default_model:
        return settings.llm_upstream_default_model.strip()
    return model.strip() or settings.llm_default_model


def _stored_user_id(user: dict[str, Any]) -> str:
    user_id = user.get("_id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ServerApiError(
            status_code=500,
            code="SERVER_INTERNAL_ERROR",
            message="Authenticated user document is missing _id.",
            error_type="server_error",
        )
    return user_id


def _mock_chat_content(prompt: str, user: dict[str, Any]) -> str:
    prompt_excerpt = prompt[:120] if prompt else "Refine the current cut."
    return (
        f"Editing focus: {prompt_excerpt} "
        f"Use the strongest motion clip as the opener, tighten redundant beats, and end on the clearest payoff. "
        f"Quota status is {user.get('quota_status', 'healthy')}."
    )


def _build_usage(messages: list[dict[str, Any]], content: str) -> dict[str, int]:
    prompt_tokens = max(32, sum(len(json.dumps(message, ensure_ascii=True)) for message in messages) // 4)
    completion_tokens = max(16, len(content) // 4)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


async def _call_upstream_chat(payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.llm_upstream_base_url or not settings.llm_upstream_api_key:
        raise ServerApiError(
            status_code=503,
            code="MODEL_PROVIDER_UNAVAILABLE",
            message="No upstream provider is configured for server chat proxy.",
            error_type="server_error",
        )
    upstream_payload = dict(payload)
    upstream_payload["model"] = _resolve_upstream_model(str(payload.get("model") or settings.llm_default_model))
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.llm_upstream_base_url.rstrip('/')}{settings.llm_upstream_chat_path}",
            json=upstream_payload,
            headers={
                "Authorization": f"Bearer {settings.llm_upstream_api_key}",
                "Content-Type": "application/json",
            },
        )
    if response.status_code >= 400:
        raise ServerApiError(
            status_code=502,
            code="MODEL_PROVIDER_UNAVAILABLE",
            message="Upstream model provider returned an error.",
            error_type="server_error",
            details={"upstream_status": response.status_code, "upstream_body": response.text[:500]},
        )
    body = response.json()
    if not isinstance(body, dict):
        raise ServerApiError(
            status_code=502,
            code="MODEL_PROVIDER_UNAVAILABLE",
            message="Upstream model provider returned an invalid response body.",
            error_type="server_error",
        )
    return body


async def _build_chat_completion_payload(
    payload: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ServerApiError(
            status_code=422,
            code="INVALID_CHAT_MESSAGES",
            message="messages must be a non-empty array.",
            error_type="invalid_request_error",
        )

    if settings.llm_proxy_mode == "upstream":
        body = await _call_upstream_chat(payload)
        usage = body.get("usage")
        body["model"] = str(payload.get("model") or settings.llm_default_model)
        body["entro_metadata"] = {
            "remaining_quota": current["user"].get("remaining_quota"),
            "quota_status": current["user"].get("quota_status", "healthy"),
            "user_id": _stored_user_id(current["user"]),
        }
        if not usage:
            body["usage"] = _build_usage(messages, json.dumps(body.get("choices", []), ensure_ascii=True))
        return body

    prompt = _extract_message_text(messages)
    content = _mock_chat_content(prompt, current["user"])
    usage = _build_usage(messages, content)
    return {
        "id": f"chatcmpl_{uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": str(payload.get("model") or settings.llm_default_model),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
        "entro_metadata": {
            "remaining_quota": current["user"].get("remaining_quota"),
            "quota_status": current["user"].get("quota_status", "healthy"),
            "user_id": _stored_user_id(current["user"]),
        },
    }


def _chunk_text(content: str, chunk_size: int = 24) -> list[str]:
    normalized = content.strip()
    if not normalized:
        return []
    return [normalized[index : index + chunk_size] for index in range(0, len(normalized), chunk_size)]


async def _mock_streaming_chat_response(body: dict[str, Any]) -> StreamingResponse:
    choice = body["choices"][0]
    content = choice["message"]["content"]
    chunks = _chunk_text(content)

    async def event_stream():
        for index, piece in enumerate(chunks):
            delta: dict[str, Any] = {"content": piece}
            if index == 0:
                delta["role"] = "assistant"
            chunk_body = {
                "id": body["id"],
                "object": "chat.completion.chunk",
                "created": body["created"],
                "model": body["model"],
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk_body, ensure_ascii=True)}\n\n"
        final_chunk = {
            "id": body["id"],
            "object": "chat.completion.chunk",
            "created": body["created"],
            "model": body["model"],
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": body["usage"],
            "entro_metadata": body["entro_metadata"],
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=True)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/health")
def health() -> dict[str, Any]:
    google_configured = bool(settings.auth_google_client_id and settings.auth_google_client_secret)
    return {
        "status": "ok",
        "service": "server",
        "version": settings.app_version,
        "phase": settings.rewrite_phase,
        "mode": "auth_phase1",
        "timestamp": now_utc().isoformat(),
        "notes": [
            "Phase 1 auth surfaces are enabled.",
            "Google OAuth is configured and ready for local testing."
            if google_configured
            else "Google OAuth is not configured yet. Set AUTH_GOOGLE_CLIENT_ID and AUTH_GOOGLE_CLIENT_SECRET.",
            "Chat proxy runs in mock mode."
            if settings.llm_proxy_mode == "mock"
            else "Chat proxy forwards requests to the configured upstream provider.",
        ],
    }


@app.get("/api/v1/runtime/capabilities", response_model=RuntimeCapabilitiesResponse)
def runtime_capabilities() -> RuntimeCapabilitiesResponse:
    return RuntimeCapabilitiesResponse(
        service="server",
        version=settings.app_version,
        phase=settings.rewrite_phase,
        mode="auth_phase1",
        retained_surfaces=[
            "health",
            "runtime_capabilities",
            "request_id_middleware",
            "auth_login_sessions",
            "auth_oauth_google",
            "auth_refresh",
            "auth_logout",
            "me",
            "chat_completions_proxy",
        ],
    )


@app.post("/api/v1/auth/login-sessions", response_model=LoginSessionCreateResponse)
def create_login_session(payload: LoginSessionCreateRequest) -> LoginSessionCreateResponse:
    login_session = oauth_service.create_login_session(payload.provider, payload.client_redirect_uri)
    authorize_url = (
        f"{settings.server_base_url.rstrip('/')}/api/v1/auth/oauth/{payload.provider}/start?"
        + urlencode({"login_session_id": login_session["login_session_id"]})
    )
    return LoginSessionCreateResponse(
        login_session_id=login_session["login_session_id"],
        authorize_url=authorize_url,
        expires_in=settings.auth_login_session_ttl_seconds,
    )


@app.get("/api/v1/auth/oauth/{provider}/start")
def start_oauth(provider: str, login_session_id: str) -> RedirectResponse:
    authorize_url = oauth_service.create_authorize_url(provider, login_session_id)
    return RedirectResponse(url=authorize_url, status_code=302)


@app.get("/api/v1/auth/oauth/{provider}/callback")
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
            "login_session_id": login_session["login_session_id"],
            "status": "authenticated",
        }
    )
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(url=f"{redirect_uri}{separator}{redirect_query}", status_code=302)


@app.get("/api/v1/auth/login-sessions/{login_session_id}", response_model=LoginSessionStatusResponse)
def get_login_session(login_session_id: str) -> LoginSessionStatusResponse:
    login_session, claimed_result = store.login_sessions.consume_once(login_session_id)
    if login_session is None:
        raise ServerApiError(
            status_code=404,
            code="LOGIN_SESSION_NOT_FOUND",
            message="The requested login session does not exist.",
            error_type="invalid_request_error",
        )
    result = claimed_result or login_session.get("result")
    return LoginSessionStatusResponse(
        login_session_id=login_session["login_session_id"],
        provider=login_session["provider"],
        status=login_session["status"],
        result=LoginSessionResult.model_validate(result) if result else None,
        error=login_session.get("error"),
    )


@app.get("/api/v1/auth/dev/fallback", response_class=HTMLResponse)
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


@app.post("/api/v1/auth/refresh", response_model=RefreshTokenResponse)
def refresh_token(payload: RefreshTokenRequest) -> RefreshTokenResponse:
    bundle = token_service.refresh_access_token(payload.refresh_token)
    return RefreshTokenResponse(
        access_token=bundle["access_token"],
        refresh_token=bundle["refresh_token"],
        expires_in=bundle["expires_in"],
        token_type=bundle["token_type"],
    )


@app.post("/api/v1/auth/logout", response_model=LogoutResponse)
def logout(current: dict[str, Any] = Depends(get_current_user)) -> LogoutResponse:
    token_service.logout(current["token_payload"]["sid"])
    return LogoutResponse()


@app.get("/api/v1/me", response_model=MeResponse)
def get_me(current: dict[str, Any] = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=user_service.user_profile(current["user"]))


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, current: dict[str, Any] = Depends(get_current_user)):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise ServerApiError(
            status_code=422,
            code="INVALID_CHAT_REQUEST",
            message="Request body must be a JSON object.",
            error_type="invalid_request_error",
        )
    if current["user"].get("status") != "active":
        raise ServerApiError(
            status_code=403,
            code="USER_SUSPENDED",
            message="The current user is suspended.",
            error_type="auth_error",
        )
    body = await _build_chat_completion_payload(payload, current)
    if payload.get("stream") is True:
        if settings.llm_proxy_mode != "mock":
            raise ServerApiError(
                status_code=501,
                code="CHAT_STREAM_NOT_SUPPORTED",
                message="Streaming is only available in mock proxy mode for now.",
                error_type="invalid_request_error",
            )
        return await _mock_streaming_chat_response(body)
    return JSONResponse(content=body)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "server",
        "phase": settings.rewrite_phase,
        "mode": "auth_phase1",
        "message": "EntroCut server now provides auth surfaces and an authenticated OpenAI-compatible chat proxy.",
        "env": {
            "mongodb_configured": bool(settings.mongodb_uri),
            "redis_configured": bool(settings.redis_url),
            "google_oauth_configured": bool(
                settings.auth_google_client_id and settings.auth_google_client_secret
            ),
            "auth_jwt_algorithm": settings.auth_jwt_algorithm,
            "llm_proxy_mode": settings.llm_proxy_mode,
            "llm_upstream_configured": bool(settings.llm_upstream_base_url and settings.llm_upstream_api_key),
        },
    }
