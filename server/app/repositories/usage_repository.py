from __future__ import annotations


class UsageRepositoryShell:
    """
    Phase 3 skeleton only.
    真实配额/计费/限流持久化后续再迁移到这里。
    """

    def get_quota_state(self, user_id: str) -> dict[str, str]:
        return {
            "user_id": user_id,
            "quota_state": "mock_ready",
        }

