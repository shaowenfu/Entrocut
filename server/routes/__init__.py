"""API 路由模块"""

from .auth import router as auth_router
from .projects import router as projects_router
from .search import router as search_router

__all__ = ["auth", "projects", "search"]
