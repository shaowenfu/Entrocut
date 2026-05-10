from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Query, Request, Response

from config import AGENT_LOOP_MAX_ITERATIONS
from contracts import (
    ChatRequest,
    ChatAnswerRequest,
    CoreApiError,
    CreateProjectRequest,
    CreateProjectResponse,
    ExportRequest,
    GetWorkspaceResponse,
    ImportAssetsRequest,
    ListProjectsResponse,
    ProjectModel,
    TaskResponse,
    UpdateProjectRequest,
)
from application.store import auth_session_store, store

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


@router.patch("/api/v1/projects/{project_id}", response_model=GetWorkspaceResponse)
async def update_project(project_id: str, payload: UpdateProjectRequest) -> GetWorkspaceResponse:
    workspace = await store.update_project_title(project_id, payload.title)
    return GetWorkspaceResponse(workspace=workspace)


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


@router.post("/api/v1/projects/{project_id}/assets/{asset_id}:retry", response_model=TaskResponse)
async def retry_asset(project_id: str, asset_id: str) -> TaskResponse:
    task = await store.queue_asset_retry(project_id, asset_id)
    return TaskResponse(task=task)


@router.delete("/api/v1/projects/{project_id}/assets/{asset_id}", response_model=GetWorkspaceResponse)
async def delete_asset(project_id: str, asset_id: str) -> GetWorkspaceResponse:
    workspace = await store.soft_delete_asset(project_id, asset_id)
    return GetWorkspaceResponse(workspace=workspace)


@router.post("/api/v1/projects/{project_id}/assets/{asset_id}:restore", response_model=GetWorkspaceResponse)
async def restore_asset(project_id: str, asset_id: str) -> GetWorkspaceResponse:
    workspace = await store.restore_asset(project_id, asset_id)
    return GetWorkspaceResponse(workspace=workspace)


@router.post("/api/v1/projects/{project_id}/chat", response_model=TaskResponse)
async def chat(project_id: str, payload: ChatRequest, request: Request) -> TaskResponse:
    routing = payload.routing.model_dump() if payload.routing else {}
    normalized_mode = "BYOK" if (routing.get("mode") or "Platform").upper() == "BYOK" else "Platform"
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
        routing,
        request.headers.get("X-BYOK-Key"),
        _agent_loop_max_iterations_resolver(),
    )
    return TaskResponse(task=task)


@router.post("/api/v1/projects/{project_id}/questions/{question_id}:answer", response_model=TaskResponse)
async def answer_question(
    project_id: str,
    question_id: str,
    payload: ChatAnswerRequest,
    request: Request,
) -> TaskResponse:
    routing = payload.routing.model_dump() if payload.routing else {}
    normalized_mode = "BYOK" if (routing.get("mode") or "Platform").upper() == "BYOK" else "Platform"
    if normalized_mode != "BYOK":
        auth_session = await auth_session_store.snapshot()
        if not auth_session.get("access_token"):
            raise CoreApiError(
                status_code=401,
                code="AUTH_SESSION_REQUIRED",
                message="Sign in is required before chat can run.",
            )
    task = await store.answer_agent_question(
        project_id,
        question_id,
        payload,
        routing,
        request.headers.get("X-BYOK-Key"),
        _agent_loop_max_iterations_resolver(),
    )
    return TaskResponse(task=task)


@router.delete("/api/v1/projects/{project_id}/chat-turns", response_model=GetWorkspaceResponse)
async def clear_chat_turns(project_id: str) -> GetWorkspaceResponse:
    workspace = await store.clear_project_chat_turns(project_id)
    return GetWorkspaceResponse(workspace=workspace)


@router.delete("/api/v1/projects/{project_id}", status_code=204, response_class=Response)
async def delete_project(project_id: str) -> Response:
    await store.delete_project(project_id)
    return Response(status_code=204)


@router.post("/api/v1/projects/{project_id}/export", response_model=TaskResponse)
async def export_project(project_id: str, payload: ExportRequest) -> TaskResponse:
    task = await store.queue_export(project_id, payload)
    return TaskResponse(task=task)
