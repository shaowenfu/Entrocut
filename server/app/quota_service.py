from __future__ import annotations

import time
from threading import Lock
from typing import Any
from uuid import uuid4

import redis
from redis import Redis
from redis.exceptions import RedisError

from .auth_store import AuthStore
from .config import Settings
from .errors import ServerApiError


def _window_id(now_ts: float | None = None) -> int:
    timestamp = now_ts if now_ts is not None else time.time()
    return int(timestamp // 60)


class RateLimitService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._redis: Redis | None = None
        self._redis_ready: bool | None = None
        self._memory_counters: dict[tuple[str, str, int], int] = {}
        self._memory_lock = Lock()

    def _requests_key(self, user_id: str, window: int) -> str:
        return f"entrocut:server:ratelimit:req:{user_id}:{window}"

    def _tokens_key(self, user_id: str, window: int) -> str:
        return f"entrocut:server:ratelimit:tok:{user_id}:{window}"

    def _get_redis(self) -> Redis | None:
        if not self._settings.redis_url:
            self._redis_ready = False
            return None
        if self._redis_ready is False:
            return None
        if self._redis is None:
            self._redis = redis.from_url(self._settings.redis_url, decode_responses=True)
        redis_client = self._redis
        if self._redis_ready is None:
            try:
                if redis_client is None:
                    return None
                redis_client.ping()
                self._redis_ready = True
            except RedisError:
                self._redis_ready = False
                raise
        return redis_client

    def ensure_connection(self) -> None:
        redis_client = self._get_redis()
        if self._settings.redis_url and redis_client is None:
            raise RedisError("Redis is configured but unavailable.")

    def _increment_memory_counter(self, kind: str, user_id: str, window: int, amount: int) -> int:
        with self._memory_lock:
            expired_windows = [key for key in self._memory_counters if key[2] < window]
            for key in expired_windows:
                self._memory_counters.pop(key, None)
            storage_key = (kind, user_id, window)
            current_value = self._memory_counters.get(storage_key, 0) + amount
            self._memory_counters[storage_key] = current_value
            return current_value

    def _increment_counter(self, kind: str, user_id: str, window: int, amount: int) -> int:
        redis_client = self._get_redis()
        if redis_client is None:
            return self._increment_memory_counter(kind, user_id, window, amount)
        key = self._requests_key(user_id, window) if kind == "requests" else self._tokens_key(user_id, window)
        pipe = redis_client.pipeline()
        pipe.incrby(key, amount)
        pipe.expire(key, 65)
        current_value, _ = pipe.execute()
        return int(current_value)

    def consume_prompt_budget(self, *, user_id: str, prompt_tokens: int) -> None:
        window = _window_id()
        request_count = self._increment_counter("requests", user_id, window, 1)
        if request_count > self._settings.rate_limit_requests_per_minute:
            raise ServerApiError(
                status_code=429,
                code="RATE_LIMITED",
                message="Requests per minute limit exceeded.",
                error_type="rate_limit_error",
                details={
                    "limit_type": "requests_per_minute",
                    "limit": self._settings.rate_limit_requests_per_minute,
                    "current": request_count,
                },
            )
        token_count = self._increment_counter("tokens", user_id, window, max(prompt_tokens, 0))
        if token_count > self._settings.rate_limit_tokens_per_minute:
            raise ServerApiError(
                status_code=429,
                code="RATE_LIMITED",
                message="Tokens per minute limit exceeded.",
                error_type="rate_limit_error",
                details={
                    "limit_type": "tokens_per_minute",
                    "limit": self._settings.rate_limit_tokens_per_minute,
                    "current": token_count,
                },
            )

    def add_completion_tokens(self, *, user_id: str, completion_tokens: int) -> None:
        if completion_tokens <= 0:
            return
        self._increment_counter("tokens", user_id, _window_id(), completion_tokens)


class QuotaService:
    def __init__(self, settings: Settings, store: AuthStore) -> None:
        self._settings = settings
        self._store = store

    def ensure_user_quota_defaults(self, user: dict[str, Any]) -> dict[str, Any]:
        user_id = user.get("_id")
        if not isinstance(user_id, str) or not user_id.strip():
            return user
        quota_total = int(user["quota_total"]) if user.get("quota_total") is not None else self._settings.quota_free_total_tokens
        remaining_quota = int(user["remaining_quota"]) if user.get("remaining_quota") is not None else quota_total
        quota_status = str(user.get("quota_status") or "healthy")
        if not {"quota_total", "remaining_quota"} <= set(user.keys()):
            self._store.mongo.initialize_user_quota(user_id, quota_total, remaining_quota, quota_status)
        user["quota_total"] = quota_total
        user["remaining_quota"] = remaining_quota
        user["quota_status"] = quota_status
        return user

    def _effective_low_watermark(self, quota_total: int) -> int:
        return min(self._settings.quota_low_watermark_tokens, max(0, quota_total // 10))

    def assert_can_chat(self, user: dict[str, Any]) -> None:
        remaining_quota = int(user.get("remaining_quota") or 0)
        quota_status = str(user.get("quota_status") or "healthy")
        if quota_status == "exhausted" or remaining_quota <= 0:
            raise ServerApiError(
                status_code=402,
                code="QUOTA_EXCEEDED",
                message="The current user has exhausted the chat quota.",
                error_type="billing_error",
                details={"remaining_quota": max(remaining_quota, 0)},
            )

    def record_chat_usage(
        self,
        *,
        user: dict[str, Any],
        session_id: str,
        request_id: str,
        exposed_model: str,
        provider_model: str | None,
        usage: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not usage:
            return user
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0)
        if total_tokens <= 0:
            return user
        updated_user = self._store.mongo.consume_user_quota(
            user_id=user["_id"],
            session_id=session_id,
            request_id=request_id or f"req_{uuid4().hex[:12]}",
            model=exposed_model,
            provider_model=provider_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            quota_total=int(user.get("quota_total") or self._settings.quota_free_total_tokens),
            low_watermark_tokens=self._effective_low_watermark(
                int(user.get("quota_total") or self._settings.quota_free_total_tokens)
            ),
        )
        user.update(
            {
                "quota_total": updated_user.get("quota_total", user.get("quota_total")),
                "remaining_quota": updated_user.get("remaining_quota", user.get("remaining_quota")),
                "quota_status": updated_user.get("quota_status", user.get("quota_status")),
            }
        )
        return user
