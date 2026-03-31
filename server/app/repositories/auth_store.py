from __future__ import annotations

from ..core.config import Settings
from .login_session_repository import LoginSessionStore
from .mongo_repository import MongoRepository


class AuthStore:
    def __init__(self, settings: Settings) -> None:
        self.mongo = MongoRepository(settings)
        self.login_sessions = LoginSessionStore(settings, self.mongo.fallback)

    def ensure_indexes(self) -> None:
        self.mongo.ensure_connection()
        self.mongo.ensure_indexes()
        self.login_sessions.ensure_connection()
