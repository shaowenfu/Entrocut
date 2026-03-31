from __future__ import annotations

import json
import math
from typing import Any
from uuid import uuid4

from ...core.errors import ServerApiError
from ...repositories.auth_store import AuthStore
from ...shared.time import now_utc


def stored_user_id(user: dict[str, Any]) -> str:
    user_id = user.get("_id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ServerApiError(
            status_code=500,
            code="SERVER_INTERNAL_ERROR",
            message="Authenticated user document is missing _id.",
            error_type="server_error",
        )
    return user_id


def build_entro_metadata(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "credits_balance": int(user.get("credits_balance") or 0),
        "user_id": stored_user_id(user),
    }


def build_usage(messages: list[dict[str, Any]], content: str) -> dict[str, int]:
    prompt_tokens = max(32, sum(len(json.dumps(message, ensure_ascii=True)) for message in messages) // 4)
    completion_tokens = max(16, len(content) // 4)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def normalize_usage(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if not all(isinstance(value, int) and value >= 0 for value in (prompt_tokens, completion_tokens)):
        return None
    normalized_total = prompt_tokens + completion_tokens
    if not isinstance(total_tokens, int) or total_tokens < 0 or total_tokens != normalized_total:
        total_tokens = normalized_total
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def resolve_rate(model: str, rate_cards: dict[str, dict[str, int]]) -> dict[str, int]:
    if model in rate_cards:
        return rate_cards[model]
    if rate_cards:
        return min(
            rate_cards.values(),
            key=lambda item: int(item.get("prompt_per_1m") or 0) + int(item.get("completion_per_1m") or 0),
        )
    raise ServerApiError(
        status_code=500,
        code="RATE_CARD_UNAVAILABLE",
        message="No rate card is configured.",
        error_type="server_error",
    )


def compute_credit_cost(model: str, prompt_tokens: int, completion_tokens: int, rate_cards: dict[str, dict[str, int]]) -> int:
    rate = resolve_rate(model, rate_cards)
    weighted_tokens = (
        int(prompt_tokens) * int(rate["prompt_per_1m"])
        + int(completion_tokens) * int(rate["completion_per_1m"])
    )
    return int(math.ceil(weighted_tokens / 1_000_000))


def settle_chat_billing(
    *,
    current: dict[str, Any],
    request_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    provider: str,
    rate_cards: dict[str, dict[str, int]],
    store: AuthStore,
) -> int:
    user_id = stored_user_id(current["user"])
    session_id = str(current["token_payload"]["sid"])
    credits_cost = compute_credit_cost(model, prompt_tokens, completion_tokens, rate_cards)
    credits_balance = (
        store.mongo.deduct_credits(user_id, credits_cost)
        if credits_cost > 0
        else int(current["user"].get("credits_balance") or 0)
    )
    store.mongo.record_ledger(
        {
            "_id": f"ledger_{uuid4().hex}",
            "request_id": request_id,
            "user_id": user_id,
            "session_id": session_id,
            "model": model,
            "usage": {
                "prompt_tokens": int(prompt_tokens),
                "completion_tokens": int(completion_tokens),
                "total_tokens": int(prompt_tokens) + int(completion_tokens),
            },
            "credits_cost": credits_cost,
            "credits_balance": credits_balance,
            "provider": provider,
            "created_at": now_utc().isoformat(),
        }
    )
    current["user"]["credits_balance"] = credits_balance
    return credits_balance
