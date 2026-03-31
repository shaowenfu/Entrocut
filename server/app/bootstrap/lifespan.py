from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..core.runtime_guard import validate_runtime_settings
from .dependencies import rate_limit_service, settings, store, update_dependency_health


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_runtime_settings(settings)
    store.ensure_indexes()
    rate_limit_service.ensure_connection()
    update_dependency_health()
    yield
