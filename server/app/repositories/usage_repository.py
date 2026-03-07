from __future__ import annotations

import os
from collections import defaultdict
from threading import Lock
from typing import Any


class UsageRepositoryShell:
    def __init__(self) -> None:
        self._lock = Lock()
        self._usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._limits = {
            "embedding": self._read_int("SERVER_EMBEDDING_MAX_REQUESTS_PER_USER"),
            "vector_search": self._read_int("SERVER_VECTOR_SEARCH_MAX_REQUESTS_PER_USER"),
        }

    def get_quota_state(self, user_id: str) -> dict[str, Any]:
        normalized_user_id = user_id.strip()
        with self._lock:
            counters = dict(self._usage.get(normalized_user_id, {}))
        return {
            "user_id": normalized_user_id,
            "quota_state": "ready",
            "limits": dict(self._limits),
            "counters": counters,
        }

    def consume(self, user_id: str, capability: str) -> dict[str, Any]:
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            return {
                "allowed": False,
                "error_code": "SERVER_VECTOR_FILTER_INVALID",
                "message": "user_id is required.",
                "retryable": False,
                "provider_status": "invalid_scope",
            }
        limit = self._limits.get(capability, 0)
        with self._lock:
            used = self._usage[normalized_user_id][capability]
            if limit > 0 and used >= limit:
                return {
                    "allowed": False,
                    "error_code": "SERVER_PROVIDER_QUOTA_EXCEEDED",
                    "message": f"{capability} quota exhausted for user {normalized_user_id}.",
                    "retryable": False,
                    "provider_status": "quota_exceeded",
                    "used": used,
                    "limit": limit,
                }
            self._usage[normalized_user_id][capability] = used + 1
            return {
                "allowed": True,
                "used": used + 1,
                "limit": limit,
            }

    @staticmethod
    def _read_int(env_name: str) -> int:
        raw_value = os.getenv(env_name, "").strip()
        if not raw_value:
            return 0
        try:
            return max(0, int(raw_value))
        except ValueError:
            return 0
