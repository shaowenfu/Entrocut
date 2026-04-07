from __future__ import annotations

from datetime import datetime, timedelta
import secrets
from typing import Any

import jwt

from ...core.config import Settings
from ...core.errors import ServerApiError
from ...repositories.auth_store import AuthStore
from ...shared.time import now_utc, to_iso
from .utils import hash_token, new_id


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
