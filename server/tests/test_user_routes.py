from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth_service import new_id
from app.auth_store import now_utc, to_iso
from app.main import app, quota_service, rate_limit_service, settings, store, token_service


def _configure_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(settings, "quota_free_total_tokens", 4321)
    monkeypatch.setattr(settings, "quota_low_watermark_tokens", 50)
    monkeypatch.setattr(settings, "rate_limit_requests_per_minute", 20)
    monkeypatch.setattr(settings, "rate_limit_tokens_per_minute", 40000)
    rate_limit_service._memory_counters.clear()
    rate_limit_service._redis = None
    rate_limit_service._redis_ready = None


def _create_user() -> dict[str, str | int | None]:
    current_time = now_utc()
    user = {
        "_id": new_id("user"),
        "email": f"{new_id('mail')}@entrocut.local",
        "display_name": "User Routes Test",
        "avatar_url": None,
        "status": "active",
        "primary_provider": "google",
        "plan": "free",
        "quota_total": 4321,
        "quota_status": "healthy",
        "remaining_quota": 4321,
        "created_at": to_iso(current_time),
        "updated_at": to_iso(current_time),
        "last_login_at": to_iso(current_time),
    }
    store.mongo.create_user(user)
    return user


def test_user_profile_requires_bearer_token() -> None:
    client = TestClient(app)

    response = client.get("/user/profile")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"


def test_user_profile_and_usage_return_expected_fields(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    quota_service.record_chat_usage(
        user=user,
        session_id=bundle["session_id"],
        request_id="req_user_usage_001",
        exposed_model="entro-reasoning-v1",
        provider_model="gemini-2.5-flash",
        usage={
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
        },
    )
    quota_service.record_chat_usage(
        user=user,
        session_id=bundle["session_id"],
        request_id="req_user_usage_002",
        exposed_model="entro-reasoning-v1",
        provider_model="gemini-2.5-flash",
        usage={
            "prompt_tokens": 30,
            "completion_tokens": 10,
            "total_tokens": 40,
        },
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {bundle['access_token']}"}

    profile_response = client.get("/user/profile", headers=headers)
    usage_response = client.get("/user/usage", headers=headers)

    assert profile_response.status_code == 200
    assert usage_response.status_code == 200
    profile_body = profile_response.json()
    usage_body = usage_response.json()
    assert profile_body["user"]["id"] == user["_id"]
    assert profile_body["user"]["plan"] == "free"
    assert usage_body["user_id"] == user["_id"]
    assert usage_body["usage"]["remaining_quota"] == 4256
    assert usage_body["usage"]["quota_total"] == 4321
    assert usage_body["usage"]["consumed_tokens_today"] == 65
    assert usage_body["usage"]["consumed_tokens_this_month"] == 65
    assert usage_body["usage"]["request_count_today"] == 2
    assert usage_body["usage"]["request_count_this_month"] == 2
    assert usage_body["usage"]["membership_plan"] == "free"
    assert usage_body["usage"]["subscription_status"] == "active"
    assert usage_body["usage"]["rate_limit_requests_per_minute"] == 20
    assert usage_body["usage"]["rate_limit_tokens_per_minute"] == 40000
