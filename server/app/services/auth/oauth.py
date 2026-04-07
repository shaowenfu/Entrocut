from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from authlib.integrations.httpx_client import AsyncOAuth2Client

from ...core.config import Settings
from ...core.errors import ServerApiError
from ...repositories.auth_store import AuthStore
from ...shared.time import now_utc, to_iso
from .utils import ProviderConfig, new_id


class OAuthService:
    def __init__(self, settings: Settings, store: AuthStore) -> None:
        self._settings = settings
        self._store = store

    def _provider_config(self, provider: str) -> ProviderConfig:
        if provider == "google":
            if not self._settings.auth_google_client_id or not self._settings.auth_google_client_secret:
                raise ServerApiError(
                    status_code=503,
                    code="OAUTH_PROVIDER_NOT_CONFIGURED",
                    message="Google OAuth is not configured on the server.",
                    error_type="server_error",
                )
            return ProviderConfig(
                name="google",
                authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",
                userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
                client_id=self._settings.auth_google_client_id,
                client_secret=self._settings.auth_google_client_secret,
                scope=self._settings.auth_google_scope,
            )
        if provider == "github":
            if not self._settings.auth_github_client_id or not self._settings.auth_github_client_secret:
                raise ServerApiError(
                    status_code=503,
                    code="OAUTH_PROVIDER_NOT_CONFIGURED",
                    message="GitHub OAuth is not configured on the server.",
                    error_type="server_error",
                )
            return ProviderConfig(
                name="github",
                authorize_url="https://github.com/login/oauth/authorize",
                token_url="https://github.com/login/oauth/access_token",
                userinfo_url="https://api.github.com/user",
                client_id=self._settings.auth_github_client_id,
                client_secret=self._settings.auth_github_client_secret,
                scope="read:user user:email",
            )
        raise ServerApiError(
            status_code=400,
            code="INVALID_REQUEST",
            message=f"Unsupported OAuth provider: {provider}.",
            error_type="invalid_request_error",
        )

    def _callback_url(self, provider: str) -> str:
        return f"{self._settings.server_base_url.rstrip('/')}/api/v1/auth/oauth/{provider}/callback"

    def create_login_session(self, provider: str, client_redirect_uri: str | None) -> dict[str, Any]:
        provider_config = self._provider_config(provider)
        created_at = now_utc()
        login_session = {
            "login_session_id": new_id("login"),
            "provider": provider_config.name,
            "status": "pending",
            "state": None,
            "pkce_verifier": None,
            "client_redirect_uri": client_redirect_uri or self._settings.default_client_redirect_uri,
            "result": None,
            "error": None,
            "created_at": to_iso(created_at),
            "expires_at": to_iso(created_at + timedelta(seconds=self._settings.auth_login_session_ttl_seconds)),
            "consumed_at": None,
        }
        self._store.login_sessions.create(login_session)
        return login_session

    def create_authorize_url(self, provider: str, login_session_id: str) -> str:
        provider_config = self._provider_config(provider)
        login_session = self._store.login_sessions.get(login_session_id)
        if login_session is None:
            raise ServerApiError(
                status_code=404,
                code="LOGIN_SESSION_NOT_FOUND",
                message="The requested login session does not exist.",
                error_type="invalid_request_error",
            )
        code_verifier = secrets.token_urlsafe(48)
        async_oauth = AsyncOAuth2Client(
            client_id=provider_config.client_id,
            client_secret=provider_config.client_secret,
            redirect_uri=self._callback_url(provider),
            scope=provider_config.scope,
            code_challenge_method="S256",
            token_endpoint_auth_method=provider_config.token_endpoint_auth_method,
        )
        authorize_url, state = async_oauth.create_authorization_url(
            provider_config.authorize_url,
            code_verifier=code_verifier,
        )
        login_session["state"] = state
        login_session["pkce_verifier"] = code_verifier
        login_session["provider"] = provider
        self._store.login_sessions.save(login_session)
        self._store.login_sessions.bind_state(login_session_id, state)
        return authorize_url

    async def handle_callback(self, provider: str, request_url: str) -> dict[str, Any]:
        provider_config = self._provider_config(provider)
        state = self._extract_query_value(request_url, "state")
        if not state:
            raise ServerApiError(
                status_code=400,
                code="INVALID_REQUEST",
                message="OAuth callback is missing state.",
                error_type="invalid_request_error",
            )
        login_session = self._store.login_sessions.find_by_state(state)
        if login_session is None:
            raise ServerApiError(
                status_code=400,
                code="INVALID_REQUEST",
                message="OAuth callback state is invalid or expired.",
                error_type="invalid_request_error",
            )
        if login_session["provider"] != provider:
            raise ServerApiError(
                status_code=400,
                code="INVALID_REQUEST",
                message="OAuth callback provider does not match login session.",
                error_type="invalid_request_error",
            )
        async with AsyncOAuth2Client(
            client_id=provider_config.client_id,
            client_secret=provider_config.client_secret,
            redirect_uri=self._callback_url(provider),
            scope=provider_config.scope,
            token_endpoint_auth_method=provider_config.token_endpoint_auth_method,
        ) as oauth_client:
            try:
                await oauth_client.fetch_token(
                    provider_config.token_url,
                    authorization_response=request_url,
                    code_verifier=login_session["pkce_verifier"],
                )
                userinfo_response = await oauth_client.get(provider_config.userinfo_url)
            except Exception as exc:
                login_session["status"] = "failed"
                login_session["error"] = {
                    "code": "OAUTH_CALLBACK_FAILED",
                    "message": str(exc) or "OAuth callback failed.",
                }
                self._store.login_sessions.save(login_session)
                raise ServerApiError(
                    status_code=502,
                    code="OAUTH_CALLBACK_FAILED",
                    message="Failed to complete provider OAuth callback.",
                    error_type="provider_error",
                ) from exc

        if userinfo_response.status_code >= 400:
            login_session["status"] = "failed"
            login_session["error"] = {
                "code": "OAUTH_USERINFO_FAILED",
                "message": "Failed to fetch provider user profile.",
            }
            self._store.login_sessions.save(login_session)
            raise ServerApiError(
                status_code=502,
                code="OAUTH_USERINFO_FAILED",
                message="Failed to fetch provider user profile.",
                error_type="provider_error",
            )
        payload = userinfo_response.json()
        if provider == "google":
            provider_user_id = payload.get("sub")
            avatar_url = payload.get("picture")
            display_name = payload.get("name")
        elif provider == "github":
            provider_user_id = str(payload.get("id")) if payload.get("id") is not None else None
            avatar_url = payload.get("avatar_url")
            display_name = payload.get("name") or payload.get("login")
        else:
            provider_user_id = None
            avatar_url = None
            display_name = None

        return {
            "login_session": login_session,
            "profile": {
                "provider_user_id": provider_user_id,
                "email": payload.get("email"),
                "display_name": display_name,
                "avatar_url": avatar_url,
            },
        }

    @staticmethod
    def _extract_query_value(url: str, field: str) -> str | None:
        from urllib.parse import parse_qs, urlparse

        values = parse_qs(urlparse(url).query).get(field)
        return values[0] if values else None
