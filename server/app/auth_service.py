from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import jwt
from authlib.integrations.httpx_client import AsyncOAuth2Client

from .auth_store import AuthStore, now_utc, to_iso
from .config import Settings
from .errors import ServerApiError


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    client_id: str
    client_secret: str
    scope: str
    token_endpoint_auth_method: str = "client_secret_post"


class TokenService:
    def __init__(self, settings: Settings, store: AuthStore) -> None:
        self._settings = settings
        self._store = store

    def issue_session_bundle(self, user: dict[str, Any]) -> dict[str, Any]:
        issued_at = now_utc()
        session_id = new_id("session")
        session_doc = {
            "_id": session_id,
            "user_id": user["_id"],
            "client_type": "electron",
            "device_label": "EntroCut Desktop",
            "status": "active",
            "created_at": to_iso(issued_at),
            "last_seen_at": to_iso(issued_at),
            "revoked_at": None,
        }
        self._store.mongo.create_auth_session(session_doc)

        access_token = jwt.encode(
            {
                "sub": user["_id"],
                "sid": session_id,
                "scope": ["user:read", "chat:proxy"],
                "iat": int(issued_at.timestamp()),
                "exp": int((issued_at + timedelta(seconds=self._settings.auth_access_token_expires_seconds)).timestamp()),
                "iss": self._settings.auth_token_issuer,
                "aud": self._settings.auth_token_audience,
            },
            self._settings.auth_jwt_secret,
            algorithm=self._settings.auth_jwt_algorithm,
        )
        refresh_token = secrets.token_urlsafe(48)
        refresh_doc = {
            "_id": new_id("rt"),
            "session_id": session_id,
            "user_id": user["_id"],
            "token_hash": hash_token(refresh_token),
            "expires_at": to_iso(issued_at + timedelta(seconds=self._settings.auth_refresh_token_expires_seconds)),
            "rotated_from": None,
            "revoked_at": None,
            "created_at": to_iso(issued_at),
        }
        self._store.mongo.store_refresh_token(refresh_doc)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": self._settings.auth_access_token_expires_seconds,
            "token_type": "Bearer",
            "session_id": session_id,
        }

    def decode_access_token(self, token: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self._settings.auth_jwt_secret,
                algorithms=[self._settings.auth_jwt_algorithm],
                audience=self._settings.auth_token_audience,
                issuer=self._settings.auth_token_issuer,
            )
        except jwt.ExpiredSignatureError as exc:
            raise ServerApiError(
                status_code=401,
                code="AUTH_TOKEN_EXPIRED",
                message="The provided access token has expired.",
                error_type="auth_error",
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise ServerApiError(
                status_code=401,
                code="AUTH_TOKEN_INVALID",
                message="The provided access token is invalid.",
                error_type="auth_error",
            ) from exc

        session = self._store.mongo.find_auth_session(payload["sid"])
        if session is None or session.get("status") != "active" or session.get("revoked_at") is not None:
            raise ServerApiError(
                status_code=401,
                code="AUTH_TOKEN_INVALID",
                message="The current auth session is no longer active.",
                error_type="auth_error",
            )
        self._store.mongo.touch_auth_session(payload["sid"], now_utc())
        return payload

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        token_hash = hash_token(refresh_token)
        refresh_doc = self._store.mongo.find_refresh_token(token_hash)
        if refresh_doc is None:
            raise ServerApiError(
                status_code=401,
                code="AUTH_TOKEN_INVALID",
                message="The provided refresh token is invalid.",
                error_type="auth_error",
            )
        if refresh_doc.get("revoked_at") is not None:
            raise ServerApiError(
                status_code=401,
                code="AUTH_TOKEN_INVALID",
                message="The provided refresh token has been revoked.",
                error_type="auth_error",
            )
        expires_at = datetime.fromisoformat(refresh_doc["expires_at"])
        if expires_at <= now_utc():
            raise ServerApiError(
                status_code=401,
                code="AUTH_TOKEN_EXPIRED",
                message="The provided refresh token has expired.",
                error_type="auth_error",
            )
        user = self._store.mongo.find_user_by_id(refresh_doc["user_id"])
        if user is None:
            raise ServerApiError(
                status_code=401,
                code="AUTH_TOKEN_INVALID",
                message="The refresh token user no longer exists.",
                error_type="auth_error",
            )
        self._store.mongo.revoke_refresh_token(token_hash, now_utc())
        return self.issue_session_bundle(user)

    def logout(self, session_id: str) -> None:
        revoked_at = now_utc()
        self._store.mongo.revoke_auth_session(session_id, revoked_at)
        self._store.mongo.revoke_session_refresh_tokens(session_id, revoked_at)


class UserService:
    def __init__(self, store: AuthStore) -> None:
        self._store = store
        self._settings = store.mongo._settings

    def upsert_user_from_provider(self, provider: str, profile: dict[str, Any]) -> dict[str, Any]:
        provider_user_id = profile["provider_user_id"]
        identity = self._store.mongo.find_identity(provider, provider_user_id)
        if identity is not None:
            user = self._store.mongo.find_user_by_id(identity["user_id"])
            if user is None:
                raise ServerApiError(
                    status_code=500,
                    code="SERVER_INTERNAL_ERROR",
                    message="Identity points to a missing user.",
                    error_type="server_error",
                )
            self._store.mongo.update_user_login(user["_id"], now_utc())
            return user

        user = None
        email = profile.get("email")
        if email:
            user = self._store.mongo.find_user_by_email(email)

        current_time = now_utc()
        if user is None:
            user = {
                "_id": new_id("user"),
                "email": email,
                "display_name": profile.get("display_name"),
                "avatar_url": profile.get("avatar_url"),
                "status": "active",
                "primary_provider": provider,
                "credits_balance": 100_000,
                "created_at": to_iso(current_time),
                "updated_at": to_iso(current_time),
                "last_login_at": to_iso(current_time),
            }
            self._store.mongo.create_user(user)
        else:
            self._store.mongo.update_user_login(user["_id"], current_time)

        identity_doc = {
            "_id": new_id("identity"),
            "user_id": user["_id"],
            "provider": provider,
            "provider_user_id": provider_user_id,
            "provider_email": email,
            "provider_profile": {
                "display_name": profile.get("display_name"),
                "avatar_url": profile.get("avatar_url"),
            },
            "created_at": to_iso(current_time),
            "updated_at": to_iso(current_time),
        }
        self._store.mongo.create_identity(identity_doc)
        return user

    @staticmethod
    def user_profile(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user["_id"],
            "email": user.get("email"),
            "display_name": user.get("display_name"),
            "avatar_url": user.get("avatar_url"),
            "status": user.get("status", "active"),
            "credits_balance": int(user.get("credits_balance") or 0),
        }

    def usage_snapshot(self, user: dict[str, Any]) -> dict[str, Any]:
        current_time = now_utc()
        day_start = datetime(current_time.year, current_time.month, current_time.day, tzinfo=UTC)
        month_start = datetime(current_time.year, current_time.month, 1, tzinfo=UTC)
        today_summary = self._store.mongo.summarize_user_usage(user_id=user["_id"], period_start=day_start)
        month_summary = self._store.mongo.summarize_user_usage(user_id=user["_id"], period_start=month_start)
        return {
            "credits_balance": int(user.get("credits_balance") or 0),
            "consumed_tokens_today": today_summary["total_tokens"],
            "consumed_tokens_this_month": month_summary["total_tokens"],
            "request_count_today": today_summary["request_count"],
            "request_count_this_month": month_summary["request_count"],
            "subscription_status": "active" if user.get("status", "active") == "active" else "inactive",
            "rate_limit_requests_per_minute": self._settings.rate_limit_requests_per_minute,
            "rate_limit_tokens_per_minute": self._settings.rate_limit_tokens_per_minute,
        }


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
