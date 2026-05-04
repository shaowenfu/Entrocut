from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ...repositories.auth_store import AuthStore
from ...shared.time import now_utc, to_iso
from .utils import new_id


class UserService:
    def __init__(self, store: AuthStore) -> None:
        self._store = store
        self._settings = store.mongo._settings

    def _quota_snapshot(self, user: dict[str, Any]) -> dict[str, int | str]:
        quota_total = int(user["quota_total"]) if user.get("quota_total") is not None else self._settings.quota_free_total_tokens
        remaining_quota = int(user["remaining_quota"]) if user.get("remaining_quota") is not None else quota_total
        quota_status = str(user.get("quota_status") or ("exhausted" if remaining_quota <= 0 else "healthy"))
        if not {"quota_total", "remaining_quota"} <= set(user.keys()):
            self._store.mongo.initialize_user_quota(user["_id"], quota_total, remaining_quota, quota_status)
        user["quota_total"] = quota_total
        user["remaining_quota"] = remaining_quota
        user["quota_status"] = quota_status
        user["credits_balance"] = remaining_quota
        return {
            "quota_total": quota_total,
            "remaining_quota": remaining_quota,
            "quota_status": quota_status,
            "credits_balance": remaining_quota,
        }

    def upsert_user_from_provider(self, provider: str, profile: dict[str, Any]) -> dict[str, Any]:
        provider_user_id = profile["provider_user_id"]
        identity = self._store.mongo.find_identity(provider, provider_user_id)
        if identity is not None:
            user = self._store.mongo.find_user_by_id(identity["user_id"])
            if user is None:
                from ...core.errors import ServerApiError

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
            quota_total = self._settings.quota_free_total_tokens
            user = {
                "_id": new_id("user"),
                "email": email,
                "display_name": profile.get("display_name"),
                "avatar_url": profile.get("avatar_url"),
                "status": "active",
                "primary_provider": provider,
                "credits_balance": quota_total,
                "quota_total": quota_total,
                "remaining_quota": quota_total,
                "quota_status": "healthy",
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

    def user_profile(self, user: dict[str, Any]) -> dict[str, Any]:
        quota = self._quota_snapshot(user)
        return {
            "id": user["_id"],
            "email": user.get("email"),
            "display_name": user.get("display_name"),
            "avatar_url": user.get("avatar_url"),
            "status": user.get("status", "active"),
            **quota,
        }

    def usage_snapshot(self, user: dict[str, Any]) -> dict[str, Any]:
        quota = self._quota_snapshot(user)
        current_time = now_utc()
        day_start = datetime(current_time.year, current_time.month, current_time.day, tzinfo=UTC)
        month_start = datetime(current_time.year, current_time.month, 1, tzinfo=UTC)
        today_summary = self._store.mongo.summarize_user_usage(user_id=user["_id"], period_start=day_start)
        month_summary = self._store.mongo.summarize_user_usage(user_id=user["_id"], period_start=month_start)
        return {
            **quota,
            "consumed_tokens_today": today_summary["total_tokens"],
            "consumed_tokens_this_month": month_summary["total_tokens"],
            "request_count_today": today_summary["request_count"],
            "request_count_this_month": month_summary["request_count"],
            "subscription_status": "active" if user.get("status", "active") == "active" else "inactive",
            "rate_limit_requests_per_minute": self._settings.rate_limit_requests_per_minute,
            "rate_limit_tokens_per_minute": self._settings.rate_limit_tokens_per_minute,
        }
