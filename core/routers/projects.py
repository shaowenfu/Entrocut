from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Query, Request

from config import AGENT_LOOP_MAX_ITERATIONS
from schemas import (
    ChatRequest,
    CoreApiError,
    CreateProjectRequest,
    CreateProjectResponse,
    ExportRequest,
    GetWorkspaceResponse,
    ImportAssetsRequest,
    ListProjectsResponse,
    ProjectModel,
    TaskResponse,
)
from store import auth_session_store, store

router = APIRouter()
_agent_loop_max_iterations_resolver: Callable[[], int] = lambda: AGENT_LOOP_MAX_ITERATIONS


def set_agent_loop_max_iterations_resolver(resolver: Callable[[], int]) -> None:
    global _agent_loop_max_iterations_resolver
    _agent_loop_max_iterations_resolver = resolver


@router.get("/api/v1/projects", response_model=ListProjectsResponse)
async def list_projects(limit: int = Query(default=20, ge=1, le=100)) -> ListProjectsResponse:
    return ListProjectsResponse(projects=store.list_projects(limit))


@router.post("/api/v1/projects", response_model=CreateProjectResponse)
async def create_project(payload: CreateProjectRequest) -> CreateProjectResponse:
    record = await store.create_project(payload)
    workspace = store.workspace_snapshot(record["project"]["id"])
    return CreateProjectResponse(project=ProjectModel.model_validate(record["project"]), workspace=workspace)


@router.get("/api/v1/projects/{project_id}", response_model=GetWorkspaceResponse)
async def get_project(project_id: str) -> GetWorkspaceResponse:
    return GetWorkspaceResponse(workspace=store.workspace_snapshot(project_id))


@router.post("/api/v1/projects/{project_id}/assets:import", response_model=TaskResponse)
async def import_assets(project_id: str, payload: ImportAssetsRequest) -> TaskResponse:
    auth_session = await auth_session_store.snapshot()
    if not auth_session.get("access_token"):
        raise CoreApiError(
            status_code=401,
            code="AUTH_SESSION_REQUIRED",
            message="Sign in is required before media ingest can run.",
        )
    task = await store.queue_assets_import(project_id, payload.media)
    return TaskResponse(task=task)


@router.post("/api/v1/projects/{project_id}/chat", response_model=TaskResponse)
async def chat(project_id: str, payload: ChatRequest, request: Request) -> TaskResponse:
    routing_mode = (request.headers.get("X-Routing-Mode") or "Platform").strip()
    normalized_mode = "BYOK" if routing_mode.upper() == "BYOK" else "Platform"
    if normalized_mode != "BYOK":
        auth_session = await auth_session_store.snapshot()
        if not auth_session.get("access_token"):
            raise CoreApiError(
                status_code=401,
                code="AUTH_SESSION_REQUIRED",
                message="Sign in is required before chat can run.",
            )
    task = await store.queue_chat(
        project_id,
        payload.prompt,
        payload.target,
        payload.model,
        normalized_mode,
        request.headers.get("X-BYOK-Key"),
        request.headers.get("X-BYOK-BaseURL"),
        _agent_loop_max_iterations_resolver(),
    )
    return TaskResponse(task=task)


@router.post("/api/v1/projects/{project_id}/export", response_model=TaskResponse)
async def export_project(project_id: str, payload: ExportRequest) -> TaskResponse:
    task = await store.queue_export(project_id, payload)
    return TaskResponse(task=task)
