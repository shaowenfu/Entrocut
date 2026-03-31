from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Any

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

from ..core.config import Settings
from ..core.errors import ServerApiError
from ..shared.time import from_iso, now_utc, to_iso


class InMemoryCollectionStore:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.identities: dict[tuple[str, str], dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.refresh_tokens: dict[str, dict[str, Any]] = {}
        self.login_sessions: dict[str, dict[str, Any]] = {}
        self.oauth_states: dict[str, str] = {}
        self.quota_ledgers: list[dict[str, Any]] = []
        self.credit_ledgers: list[dict[str, Any]] = []
        self.lock = Lock()


class MongoRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: MongoClient[Any] | None = None
        self._db: Database[Any] | None = None
        self._fallback = InMemoryCollectionStore()
        self._indexes_ready = False

    @property
    def is_persistent(self) -> bool:
        return bool(self._settings.mongodb_uri)

    @property
    def fallback(self) -> InMemoryCollectionStore:
        return self._fallback

    def _db_or_none(self) -> Database[Any] | None:
        if not self._settings.mongodb_uri:
            if not self._settings.allow_inmemory_mongo_fallback:
                raise ServerApiError(
                    status_code=503,
                    code="DEPENDENCY_UNAVAILABLE",
                    message="MongoDB fallback is disabled and MONGODB_URI is missing.",
                    error_type="server_error",
                )
            return None
        if self._db is None:
            self._client = MongoClient(self._settings.mongodb_uri, serverSelectionTimeoutMS=1500)
            self._db = self._client[self._settings.mongodb_db_name]
        return self._db

    def ensure_connection(self) -> None:
        if not self._settings.mongodb_uri:
            return
        db = self._db_or_none()
        if db is None:
            return
        db.client.admin.command("ping")

    def _collection(self, name: str) -> Collection[Any] | None:
        db = self._db_or_none()
        if db is None:
            return None
        return db[name]

    def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        try:
            users = self._collection("users")
            identities = self._collection("auth_identities")
            refresh_tokens = self._collection("refresh_tokens")
            sessions = self._collection("auth_sessions")
            quota_ledgers = self._collection("quota_ledgers")
            credit_ledgers = self._collection("credit_ledgers")
            rate_cards = self._collection("rate_cards")
            if users is None or identities is None or refresh_tokens is None or sessions is None:
                self._indexes_ready = True
                return
            users.create_index([("email", ASCENDING)], unique=True, sparse=True)
            identities.create_index([("provider", ASCENDING), ("provider_user_id", ASCENDING)], unique=True)
            refresh_tokens.create_index([("token_hash", ASCENDING)], unique=True)
            refresh_tokens.create_index([("session_id", ASCENDING)])
            sessions.create_index([("user_id", ASCENDING)])
            if quota_ledgers is not None:
                quota_ledgers.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)])
                quota_ledgers.create_index([("request_id", ASCENDING)], unique=True, sparse=True)
            if credit_ledgers is not None:
                credit_ledgers.create_index([("user_id", ASCENDING), ("created_at", ASCENDING)])
                credit_ledgers.create_index([("request_id", ASCENDING)], unique=True, sparse=True)
            if rate_cards is not None:
                rate_cards.create_index([("model", ASCENDING)], unique=True)
            self._indexes_ready = True
        except PyMongoError:
            self._indexes_ready = False
            raise

    def find_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        users = self._collection("users")
        if users is None:
            return self._fallback.users.get(user_id)
        return users.find_one({"_id": user_id})

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        users = self._collection("users")
        if users is None:
            for user in self._fallback.users.values():
                if user.get("email") == email:
                    return user
            return None
        return users.find_one({"email": email})

    def create_user(self, user_doc: dict[str, Any]) -> dict[str, Any]:
        users = self._collection("users")
        if users is None:
            with self._fallback.lock:
                self._fallback.users[user_doc["_id"]] = user_doc
            return user_doc
        users.insert_one(user_doc)
        return user_doc

    def update_user_login(self, user_id: str, logged_at: datetime) -> None:
        users = self._collection("users")
        update_doc = {"$set": {"last_login_at": to_iso(logged_at), "updated_at": to_iso(logged_at)}}
        if users is None:
            with self._fallback.lock:
                user = self._fallback.users[user_id]
                user.update(update_doc["$set"])
            return
        users.update_one({"_id": user_id}, update_doc)

    def initialize_user_quota(self, user_id: str, quota_total: int, remaining_quota: int, quota_status: str) -> None:
        users = self._collection("users")
        update_fields = {
            "quota_total": quota_total,
            "remaining_quota": remaining_quota,
            "quota_status": quota_status,
            "updated_at": to_iso(now_utc()),
        }
        if users is None:
            with self._fallback.lock:
                user = self._fallback.users.get(user_id)
                if user is not None:
                    user.update(update_fields)
            return
        users.update_one({"_id": user_id}, {"$set": update_fields})

    def consume_user_quota(
        self,
        *,
        user_id: str,
        session_id: str,
        request_id: str,
        model: str,
        provider_model: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        quota_total: int,
        low_watermark_tokens: int,
    ) -> dict[str, Any]:
        updated_at = to_iso(now_utc())
        if total_tokens <= 0:
            user = self.find_user_by_id(user_id)
            if user is None:
                raise KeyError(user_id)
            return user
        users = self._collection("users")
        quota_ledgers = self._collection("quota_ledgers")
        if users is None:
            with self._fallback.lock:
                user = self._fallback.users[user_id]
                current_remaining = int(user["remaining_quota"]) if user.get("remaining_quota") is not None else quota_total
                next_remaining = max(0, current_remaining - total_tokens)
                next_status = "exhausted" if next_remaining == 0 else ("low" if next_remaining <= low_watermark_tokens else "healthy")
                user.update(
                    {
                        "quota_total": int(user["quota_total"]) if user.get("quota_total") is not None else quota_total,
                        "remaining_quota": next_remaining,
                        "quota_status": next_status,
                        "updated_at": updated_at,
                    }
                )
                self._fallback.quota_ledgers.append(
                    {
                        "_id": request_id,
                        "request_id": request_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "model": model,
                        "provider_model": provider_model,
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total_tokens,
                        },
                        "remaining_quota": next_remaining,
                        "created_at": updated_at,
                    }
                )
                return dict(user)

        user = users.find_one({"_id": user_id})
        if user is None:
            raise KeyError(user_id)
        current_total = int(user["quota_total"]) if user.get("quota_total") is not None else quota_total
        current_remaining = int(user["remaining_quota"]) if user.get("remaining_quota") is not None else current_total
        next_remaining = max(0, current_remaining - total_tokens)
        next_status = "exhausted" if next_remaining == 0 else ("low" if next_remaining <= low_watermark_tokens else "healthy")
        updated_user = users.find_one_and_update(
            {"_id": user_id},
            {
                "$set": {
                    "quota_total": current_total,
                    "remaining_quota": next_remaining,
                    "quota_status": next_status,
                    "updated_at": updated_at,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if quota_ledgers is not None:
            quota_ledgers.insert_one(
                {
                    "_id": request_id,
                    "request_id": request_id,
                    "user_id": user_id,
                    "session_id": session_id,
                    "model": model,
                    "provider_model": provider_model,
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                    "remaining_quota": next_remaining,
                    "created_at": updated_at,
                }
            )
        return updated_user or users.find_one({"_id": user_id}) or user

    def deduct_credits(self, user_id: str, amount: int) -> int:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        users = self._collection("users")
        if users is None:
            with self._fallback.lock:
                user = self._fallback.users.get(user_id)
                if user is None:
                    raise KeyError(user_id)
                next_balance = int(user.get("credits_balance") or 0) - amount
                user["credits_balance"] = next_balance
                user["updated_at"] = to_iso(now_utc())
                return next_balance

        updated_user = users.find_one_and_update(
            {"_id": user_id},
            {"$inc": {"credits_balance": -amount}, "$set": {"updated_at": to_iso(now_utc())}},
            return_document=ReturnDocument.AFTER,
        )
        if updated_user is None:
            raise KeyError(user_id)
        return int(updated_user.get("credits_balance") or 0)

    def record_ledger(self, ledger_doc: dict[str, Any]) -> None:
        credit_ledgers = self._collection("credit_ledgers")
        if credit_ledgers is None:
            with self._fallback.lock:
                self._fallback.credit_ledgers.append(dict(ledger_doc))
            return
        credit_ledgers.insert_one(dict(ledger_doc))

    def summarize_user_usage(self, *, user_id: str, period_start: datetime) -> dict[str, int]:
        period_start_iso = to_iso(period_start)
        if period_start_iso is None:
            raise ValueError("period_start is required")
        quota_ledgers = self._collection("quota_ledgers")
        if quota_ledgers is None:
            with self._fallback.lock:
                ledgers = [ledger for ledger in self._fallback.quota_ledgers if ledger.get("user_id") == user_id]
            consumed_tokens = 0
            request_count = 0
            for ledger in ledgers:
                created_at_raw = ledger.get("created_at")
                created_at = from_iso(created_at_raw) if isinstance(created_at_raw, str) else None
                if created_at is None or created_at < period_start:
                    continue
                total_tokens = int((ledger.get("usage") or {}).get("total_tokens") or 0)
                consumed_tokens += total_tokens
                request_count += 1
            return {"request_count": request_count, "total_tokens": consumed_tokens}

        summary_pipeline = [
            {"$match": {"user_id": user_id, "created_at": {"$gte": period_start_iso}}},
            {"$group": {"_id": None, "request_count": {"$sum": 1}, "total_tokens": {"$sum": "$usage.total_tokens"}}},
        ]
        result = list(quota_ledgers.aggregate(summary_pipeline))
        if not result:
            return {"request_count": 0, "total_tokens": 0}
        summary = result[0]
        return {
            "request_count": int(summary.get("request_count") or 0),
            "total_tokens": int(summary.get("total_tokens") or 0),
        }

    def find_identity(self, provider: str, provider_user_id: str) -> dict[str, Any] | None:
        identities = self._collection("auth_identities")
        if identities is None:
            return self._fallback.identities.get((provider, provider_user_id))
        return identities.find_one({"provider": provider, "provider_user_id": provider_user_id})

    def create_identity(self, identity_doc: dict[str, Any]) -> dict[str, Any]:
        identities = self._collection("auth_identities")
        if identities is None:
            with self._fallback.lock:
                self._fallback.identities[(identity_doc["provider"], identity_doc["provider_user_id"])] = identity_doc
            return identity_doc
        identities.insert_one(identity_doc)
        return identity_doc

    def create_auth_session(self, session_doc: dict[str, Any]) -> dict[str, Any]:
        sessions = self._collection("auth_sessions")
        if sessions is None:
            with self._fallback.lock:
                self._fallback.sessions[session_doc["_id"]] = session_doc
            return session_doc
        sessions.insert_one(session_doc)
        return session_doc

    def find_auth_session(self, session_id: str) -> dict[str, Any] | None:
        sessions = self._collection("auth_sessions")
        if sessions is None:
            return self._fallback.sessions.get(session_id)
        return sessions.find_one({"_id": session_id})

    def revoke_auth_session(self, session_id: str, revoked_at: datetime) -> None:
        sessions = self._collection("auth_sessions")
        update_doc = {
            "$set": {
                "status": "revoked",
                "revoked_at": to_iso(revoked_at),
                "last_seen_at": to_iso(revoked_at),
            }
        }
        if sessions is None:
            with self._fallback.lock:
                session = self._fallback.sessions.get(session_id)
                if session:
                    session.update(update_doc["$set"])
            return
        sessions.update_one({"_id": session_id}, update_doc)

    def touch_auth_session(self, session_id: str, seen_at: datetime) -> None:
        sessions = self._collection("auth_sessions")
        update_doc = {"$set": {"last_seen_at": to_iso(seen_at)}}
        if sessions is None:
            with self._fallback.lock:
                session = self._fallback.sessions.get(session_id)
                if session:
                    session.update(update_doc["$set"])
            return
        sessions.update_one({"_id": session_id}, update_doc)

    def store_refresh_token(self, refresh_doc: dict[str, Any]) -> dict[str, Any]:
        refresh_tokens = self._collection("refresh_tokens")
        if refresh_tokens is None:
            with self._fallback.lock:
                self._fallback.refresh_tokens[refresh_doc["token_hash"]] = refresh_doc
            return refresh_doc
        refresh_tokens.insert_one(refresh_doc)
        return refresh_doc

    def find_refresh_token(self, token_hash: str) -> dict[str, Any] | None:
        refresh_tokens = self._collection("refresh_tokens")
        if refresh_tokens is None:
            return self._fallback.refresh_tokens.get(token_hash)
        return refresh_tokens.find_one({"token_hash": token_hash})

    def revoke_refresh_token(self, token_hash: str, revoked_at: datetime) -> None:
        refresh_tokens = self._collection("refresh_tokens")
        update_doc = {"$set": {"revoked_at": to_iso(revoked_at)}}
        if refresh_tokens is None:
            with self._fallback.lock:
                token = self._fallback.refresh_tokens.get(token_hash)
                if token:
                    token.update(update_doc["$set"])
            return
        refresh_tokens.update_one({"token_hash": token_hash}, update_doc)

    def revoke_session_refresh_tokens(self, session_id: str, revoked_at: datetime) -> None:
        refresh_tokens = self._collection("refresh_tokens")
        update_doc = {"$set": {"revoked_at": to_iso(revoked_at)}}
        if refresh_tokens is None:
            with self._fallback.lock:
                for token in self._fallback.refresh_tokens.values():
                    if token.get("session_id") == session_id and token.get("revoked_at") is None:
                        token.update(update_doc["$set"])
            return
        refresh_tokens.update_many({"session_id": session_id, "revoked_at": None}, update_doc)
