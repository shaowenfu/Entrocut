from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError
import redis
from redis import Redis
from redis.exceptions import RedisError

from .config import Settings


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class InMemoryCollectionStore:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.identities: dict[tuple[str, str], dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.refresh_tokens: dict[str, dict[str, Any]] = {}
        self.login_sessions: dict[str, dict[str, Any]] = {}
        self.oauth_states: dict[str, str] = {}
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

    def _db_or_none(self) -> Database[Any] | None:
        if not self._settings.mongodb_uri:
            return None
        if self._db is None:
            self._client = MongoClient(self._settings.mongodb_uri, serverSelectionTimeoutMS=1500)
            self._db = self._client[self._settings.mongodb_db_name]
        return self._db

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
            if users is None or identities is None or refresh_tokens is None or sessions is None:
                self._indexes_ready = True
                return
            users.create_index([("email", ASCENDING)], unique=True, sparse=True)
            identities.create_index([("provider", ASCENDING), ("provider_user_id", ASCENDING)], unique=True)
            refresh_tokens.create_index([("token_hash", ASCENDING)], unique=True)
            refresh_tokens.create_index([("session_id", ASCENDING)])
            sessions.create_index([("user_id", ASCENDING)])
            self._indexes_ready = True
        except PyMongoError:
            self._indexes_ready = True

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


class LoginSessionStore:
    def __init__(self, settings: Settings, memory_store: InMemoryCollectionStore) -> None:
        self._settings = settings
        self._memory_store = memory_store
        self._redis: Redis[str] | None = None
        self._redis_ready: bool | None = None

    def _session_key(self, login_session_id: str) -> str:
        return f"entrocut:server:login_session:{login_session_id}"

    def _state_key(self, state: str) -> str:
        return f"entrocut:server:oauth_state:{state}"

    def _get_redis(self) -> Redis[str] | None:
        if not self._settings.redis_url:
            self._redis_ready = False
            return None
        if self._redis_ready is False:
            return None
        if self._redis is None:
            self._redis = redis.from_url(self._settings.redis_url, decode_responses=True)
        if self._redis_ready is None:
            try:
                self._redis.ping()
                self._redis_ready = True
            except RedisError:
                self._redis_ready = False
                return None
        return self._redis

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


class AuthStore:
    def __init__(self, settings: Settings) -> None:
        self.mongo = MongoRepository(settings)
        self.login_sessions = LoginSessionStore(settings, self.mongo._fallback)

    def ensure_indexes(self) -> None:
        self.mongo.ensure_indexes()
