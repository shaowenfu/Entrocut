from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..api.router import api_router
from .dependencies import settings
from .exception_handlers import register_exception_handlers
from .lifespan import lifespan
from .middleware import register_middleware


app = FastAPI(title="EntroCut Server", version=settings.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
register_middleware(app)
app.include_router(api_router)
