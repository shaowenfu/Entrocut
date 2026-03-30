from fastapi import APIRouter

from routers.auth import router as auth_router
from routers.projects import router as projects_router
from routers.system import router as system_router

api_router = APIRouter()
api_router.include_router(projects_router)
api_router.include_router(auth_router)
api_router.include_router(system_router)
