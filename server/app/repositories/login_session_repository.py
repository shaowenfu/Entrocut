from __future__ import annotations

import json
from typing import Any

import redis
from redis import Redis
from redis.exceptions import RedisError

from ..core.config import Settings
from ..shared.time import now_utc, to_iso
from .mongo_repository import InMemoryCollectionStore


class LoginSessionStore:
    def __init__(self, settings: Settings, memory_store: InMemoryCollectionStore) -> None:
        self._settings = settings
        self._memory_store = memory_store
        self._redis: Redis | None = None
        self._redis_ready: bool | None = None

    def _session_key(self, login_session_id: str) -> str:
        return f"entrocut:server:login_session:{login_session_id}"

    def _state_key(self, state: str) -> str:
        return f"entrocut:server:oauth_state:{state}"

    def _get_redis(self) -> Redis | None:
        if not self._settings.redis_url:
            self._redis_ready = False
            if not self._settings.allow_inmemory_redis_fallback:
                raise RedisError("Redis fallback is disabled and REDIS_URL is missing.")
            return None
        if self._redis_ready is False:
            if not self._settings.allow_inmemory_redis_fallback:
                raise RedisError("Redis is unavailable and fallback is disabled.")
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
                if not self._settings.allow_inmemory_redis_fallback:
                    raise
                return None
        return redis_client

    def ensure_connection(self) -> None:
        redis_client = self._get_redis()
        if self._settings.redis_url and redis_client is None:
            raise RedisError("Redis is configured but unavailable.")

    def create(self, login_session: dict[str, Any]) -> dict[str, Any]:
        redis_client = self._get_redis()
        if redis_client is None:
            with self._memory_store.lock:
                self._memory_store.login_sessions[login_session["login_session_id"]] = login_session
            return login_session
        redis_client.setex(
            self._session_key(login_session["login_session_id"]),
            self._settings.auth_login_session_ttl_seconds,
            json.dumps(login_session),
        )
        return login_session

    def get(self, login_session_id: str) -> dict[str, Any] | None:
        redis_client = self._get_redis()
        if redis_client is None:
            record = self._memory_store.login_sessions.get(login_session_id)
            return dict(record) if record else None
        raw = redis_client.get(self._session_key(login_session_id))
        return json.loads(raw) if raw else None

    def save(self, login_session: dict[str, Any]) -> dict[str, Any]:
        redis_client = self._get_redis()
        if redis_client is None:
            with self._memory_store.lock:
                self._memory_store.login_sessions[login_session["login_session_id"]] = login_session
            return login_session
        redis_client.setex(
            self._session_key(login_session["login_session_id"]),
            self._settings.auth_login_session_ttl_seconds,
            json.dumps(login_session),
        )
        return login_session

    def bind_state(self, login_session_id: str, state: str) -> None:
        redis_client = self._get_redis()
        if redis_client is None:
            with self._memory_store.lock:
                self._memory_store.oauth_states[state] = login_session_id
            return
        redis_client.setex(self._state_key(state), self._settings.auth_login_session_ttl_seconds, login_session_id)

    def find_by_state(self, state: str) -> dict[str, Any] | None:
        redis_client = self._get_redis()
        if redis_client is None:
            login_session_id = self._memory_store.oauth_states.get(state)
            return self.get(login_session_id) if login_session_id else None
        login_session_id = redis_client.get(self._state_key(state))
        return self.get(login_session_id) if login_session_id else None

    def consume_once(self, login_session_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        record = self.get(login_session_id)
        if record is None:
            return None, None

        claimed_result = None
        if record["status"] == "authenticated":
            claimed_result = record.get("result")
            record["status"] = "consumed"
            record["consumed_at"] = to_iso(now_utc())
            record["result"] = None
            self.save(record)
        return record, claimed_result
