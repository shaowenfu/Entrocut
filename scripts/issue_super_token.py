#!/usr/bin/env python
"""Issue a long-lived access token for a dev superuser.

Creates (or reuses) a real user + session in MongoDB and signs a JWT
with an expiry far in the future.  The resulting token passes through
the full decode_access_token flow without any server-side changes.

Usage:
    python scripts/issue_super_token.py [--user-id USER_ID] [--email EMAIL]
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import jwt  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.repositories.auth_store import AuthStore  # noqa: E402
from app.services.auth.utils import new_id  # noqa: E402
from app.shared.time import now_utc, to_iso  # noqa: E402

# Far-future expiry — effectively never expires.
_EXPIRY_YEARS = 100


def _ensure_user(store: AuthStore, user_id: str, email: str) -> dict:
    """Return existing user or create a new one."""
    existing = store.mongo.find_user_by_id(user_id)
    if existing is not None:
        return existing

    now = now_utc()
    user_doc = {
        "_id": user_id,
        "email": email,
        "display_name": "Dev Superuser",
        "avatar_url": None,
        "status": "active",
        "primary_provider": "dev",
        "credits_balance": 999_999_999,
        "quota_total": 999_999_999,
        "remaining_quota": 999_999_999,
        "quota_status": "healthy",
        "created_at": to_iso(now),
        "updated_at": to_iso(now),
        "last_login_at": to_iso(now),
    }
    return store.mongo.create_user(user_doc)


def _ensure_session(store: AuthStore, session_id: str, user_id: str) -> dict:
    """Return existing session or create a new one."""
    existing = store.mongo.find_auth_session(session_id)
    if existing is not None:
        return existing

    now = now_utc()
    session_doc = {
        "_id": session_id,
        "user_id": user_id,
        "client_type": "admin_cli",
        "device_label": "Dev Superuser Token",
        "status": "active",
        "created_at": to_iso(now),
        "last_seen_at": to_iso(now),
        "revoked_at": None,
    }
    return store.mongo.create_auth_session(session_doc)


def _sign_jwt(settings, user_id: str, session_id: str) -> str:
    """Sign a JWT that expires far in the future."""
    now = now_utc()
    payload = {
        "sub": user_id,
        "sid": session_id,
        "scope": ["user:read", "chat:proxy"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=365 * _EXPIRY_YEARS)).timestamp()),
        "iss": settings.auth_token_issuer,
        "aud": settings.auth_token_audience,
    }
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue a long-lived dev superuser token")
    parser.add_argument("--user-id", default="dev_superuser", help="User ID (default: dev_superuser)")
    parser.add_argument("--email", default="dev-superuser@entrocut.local", help="Email (default: dev-superuser@entrocut.local)")
    args = parser.parse_args()

    settings = get_settings()
    store = AuthStore(settings)
    store.ensure_indexes()

    user = _ensure_user(store, args.user_id, args.email)
    session_id = f"session_dev_{args.user_id}"
    _ensure_session(store, session_id, args.user_id)

    token = _sign_jwt(settings, args.user_id, session_id)

    print(f"User ID    : {user['_id']}")
    print(f"Session ID : {session_id}")
    print(f"Access Token:\n{token}")


if __name__ == "__main__":
    main()
