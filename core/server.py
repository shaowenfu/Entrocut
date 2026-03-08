from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

APP_VERSION = "0.8.0-edit-draft"
REWRITE_PHASE = "clean_room_rewrite"
CORE_MODE = "prototype_backed"

app = FastAPI(title="EntroCut Core In-Memory", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ProjectWorkflowState = Literal[
    "prompt_input_required",
    "awaiting_media",
    "media_ready",
    "media_processing",
    "chat_thinking",
    "ready",
    "rendering",
    "failed",
]
AssetType = Literal["video", "audio"]
TaskType = Literal["ingest", "index", "chat", "render"]
TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
EditDraftStatus = Literal["draft", "ready", "rendering", "failed"]
LockedShotField = Literal["source_range", "order", "clip_id", "enabled"]
LockedSceneField = Literal["shot_ids", "order", "enabled", "intent"]
DecisionType = Literal["EDIT_DRAFT_PATCH"]


class CoreApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class RuntimeCapabilitiesResponse(BaseModel):
    service: str
    version: str
    phase: str
    mode: str
    retained_surfaces: list[str]


class MediaFileReference(BaseModel):
    name: str
    path: str | None = None
    size_bytes: int | None = None
    mime_type: str | None = None


class MediaReference(BaseModel):
    folder_path: str | None = None
    files: list[MediaFileReference] = Field(default_factory=list)


class ProjectModel(BaseModel):
    id: str
    title: str
    workflow_state: ProjectWorkflowState
    created_at: str
    updated_at: str


class AssetModel(BaseModel):
    id: str
    name: str
    duration_ms: int
    type: AssetType
    source_path: str | None = None


class ClipModel(BaseModel):
    id: str
    asset_id: str
    source_start_ms: int
    source_end_ms: int
    visual_desc: str
    semantic_tags: list[str]
    confidence: float | None = None
    thumbnail_ref: str | None = None


class ShotModel(BaseModel):
    id: str
    clip_id: str
    source_in_ms: int
    source_out_ms: int
    order: int
    enabled: bool
    label: str | None = None
    intent: str | None = None
    note: str | None = None
    locked_fields: list[LockedShotField] = Field(default_factory=list)


class SceneModel(BaseModel):
    id: str
    shot_ids: list[str]
    order: int
    enabled: bool
    label: str | None = None
    intent: str | None = None
    note: str | None = None
    locked_fields: list[LockedSceneField] = Field(default_factory=list)


class EditDraftModel(BaseModel):
    id: str
    project_id: str
    version: int
    status: EditDraftStatus
    assets: list[AssetModel]
    clips: list[ClipModel]
    shots: list[ShotModel]
    scenes: list[SceneModel] | None = None
    selected_scene_id: str | None = None
    selected_shot_id: str | None = None
    created_at: str
    updated_at: str


class UserTurnModel(BaseModel):
    id: str
    role: Literal["user"]
    content: str


class AssistantDecisionOperationModel(BaseModel):
    id: str
    action: str
    target: str
    summary: str


class AssistantDecisionTurnModel(BaseModel):
    id: str
    role: Literal["assistant"]
    type: Literal["decision"]
    decision_type: DecisionType
    reasoning_summary: str
    ops: list[AssistantDecisionOperationModel]


ChatTurnModel = UserTurnModel | AssistantDecisionTurnModel


class TaskModel(BaseModel):
    id: str
    type: TaskType
    status: TaskStatus
    progress: int | None = None
    message: str | None = None
    created_at: str
    updated_at: str


class WorkspaceSnapshotModel(BaseModel):
    project: ProjectModel
    edit_draft: EditDraftModel
    chat_turns: list[ChatTurnModel]
    active_task: TaskModel | None = None


class CreateProjectRequest(BaseModel):
    title: str | None = None
    prompt: str | None = None
    media: MediaReference | None = None


class CreateProjectResponse(BaseModel):
    project: ProjectModel
    workspace: WorkspaceSnapshotModel


class ListProjectsResponse(BaseModel):
    projects: list[ProjectModel]


class GetWorkspaceResponse(BaseModel):
    workspace: WorkspaceSnapshotModel


class ImportAssetsRequest(BaseModel):
    media: MediaReference


class ChatTarget(BaseModel):
    scene_id: str | None = None
    shot_id: str | None = None


class ChatRequest(BaseModel):
    prompt: str
    target: ChatTarget | None = None


class ExportRequest(BaseModel):
    format: str | None = None
    quality: str | None = None


class TaskResponse(BaseModel):
    task: TaskModel


class EventEnvelope(BaseModel):
    sequence: int
    event: str
    project_id: str
    emitted_at: str
    data: dict[str, Any]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def _entity_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _derive_title(title: str | None, prompt: str | None, media: MediaReference | None) -> str:
    explicit = _trimmed(title)
    if explicit:
        return explicit
    normalized_prompt = _trimmed(prompt)
    if normalized_prompt:
        return normalized_prompt[:48]
    if media and media.folder_path:
        return Path(media.folder_path).name or "Untitled Project"
    if media and media.files:
        return media.files[0].name
    return "Untitled Project"


def _media_file_refs(media: MediaReference) -> list[MediaFileReference]:
    if media.files:
        return media.files
    if media.folder_path:
        folder_name = Path(media.folder_path).name or "media"
        return [MediaFileReference(name=f"{folder_name}.mp4", path=media.folder_path)]
    return []


def _build_assets(media: MediaReference) -> list[AssetModel]:
    assets: list[AssetModel] = []
    for index, file_ref in enumerate(_media_file_refs(media), start=1):
        name = file_ref.name.strip()
        if not name:
            continue
        asset_type: AssetType = "audio" if name.lower().endswith((".mp3", ".wav", ".aac")) else "video"
        duration_seconds = 18 + index * 7
        assets.append(
            AssetModel(
                id=_entity_id("asset"),
                name=name,
                duration_ms=duration_seconds * 1000,
                type=asset_type,
                source_path=file_ref.path.strip() if file_ref.path and file_ref.path.strip() else None,
            )
        )
    return assets


def _build_clips(assets: list[AssetModel]) -> list[ClipModel]:
    clips: list[ClipModel] = []
    semantic_bank = [
        ["wide", "establishing", "environment"],
        ["action", "subject", "motion"],
        ["detail", "texture", "closeup"],
        ["transition", "reaction", "cutaway"],
    ]
    for asset_index, asset in enumerate(assets, start=1):
        for offset in range(2):
            clip_index = (asset_index - 1) * 2 + offset
            start_ms = offset * 6000
            end_ms = start_ms + 6000
            semantic_tags = semantic_bank[clip_index % len(semantic_bank)]
            clips.append(
                ClipModel(
                    id=_entity_id("clip"),
                    asset_id=asset.id,
                    source_start_ms=start_ms,
                    source_end_ms=end_ms,
                    visual_desc=f"{asset.name} candidate highlight {offset + 1}",
                    semantic_tags=semantic_tags,
                    confidence=round(0.92 - clip_index * 0.05, 2),
                    thumbnail_ref=f"thumb-gradient-{(clip_index % 4) + 1}",
                )
            )
    return clips


def _draft_from_payload(project_id: str, created_at: str, media: MediaReference | None) -> EditDraftModel:
    assets = _build_assets(media) if media else []
    clips = _build_clips(assets)
    return EditDraftModel(
        id=_entity_id("draft"),
        project_id=project_id,
        version=1,
        status="draft",
        assets=assets,
        clips=clips,
        shots=[],
        scenes=None,
        selected_scene_id=None,
        selected_shot_id=None,
        created_at=created_at,
        updated_at=created_at,
    )


def _bump_draft(draft: EditDraftModel, **changes: Any) -> EditDraftModel:
    next_version = int(changes.pop("version", draft.version + 1))
    next_updated_at = str(changes.pop("updated_at", _now_iso()))
    return draft.model_copy(update={"version": next_version, "updated_at": next_updated_at, **changes})


def _build_edit_plan(clips: list[ClipModel], prompt: str) -> tuple[list[ShotModel], list[SceneModel]]:
    selected = clips[: min(3, len(clips))]
    base_prompt = _trimmed(prompt) or "Generate a tighter first cut"
    shot_labels = ["Open", "Lift", "Payoff"]
    shots: list[ShotModel] = []
    scenes: list[SceneModel] = []

    for index, clip in enumerate(selected):
        shot_duration_ms = min(clip.source_end_ms - clip.source_start_ms, 4000 + index * 1000)
        source_in_ms = clip.source_start_ms
        source_out_ms = source_in_ms + shot_duration_ms
        shot = ShotModel(
            id=_entity_id("shot"),
            clip_id=clip.id,
            source_in_ms=source_in_ms,
            source_out_ms=source_out_ms,
            order=index,
            enabled=True,
            label=shot_labels[index] if index < len(shot_labels) else f"Shot {index + 1}",
            intent=f"{base_prompt[:60]} | {clip.visual_desc}",
            note=None,
            locked_fields=[],
        )
        shots.append(shot)
        scenes.append(
            SceneModel(
                id=_entity_id("scene"),
                shot_ids=[shot.id],
                order=index,
                enabled=True,
                label=shot.label,
                intent=shot.intent,
                note=None,
                locked_fields=[],
            )
        )

    return shots, scenes


class InMemoryProjectStore:
    def __init__(self) -> None:
        self._projects: dict[str, dict[str, Any]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    def list_projects(self, limit: int) -> list[ProjectModel]:
        ordered = sorted(self._projects.values(), key=lambda item: item["project"]["updated_at"], reverse=True)
        return [ProjectModel.model_validate(item["project"]) for item in ordered[:limit]]

    def get_project_or_raise(self, project_id: str) -> dict[str, Any]:
        project = self._projects.get(project_id)
        if project is None:
            raise CoreApiError(
                status_code=404,
                code="PROJECT_NOT_FOUND",
                message="Project not found.",
                details={"project_id": project_id},
            )
        return project

    async def create_project(self, payload: CreateProjectRequest) -> dict[str, Any]:
        normalized_prompt = _trimmed(payload.prompt)
        normalized_title = _trimmed(payload.title)
        if normalized_prompt is None and payload.media is None and normalized_title is None:
            raise CoreApiError(
                status_code=422,
                code="PROJECT_INPUT_REQUIRED",
                message="At least one of title, prompt, or media is required to create a project.",
            )

        now = _now_iso()
        project_id = _entity_id("proj")
        title = _derive_title(normalized_title, normalized_prompt, payload.media)
        edit_draft = _draft_from_payload(project_id, now, payload.media)
        if edit_draft.assets:
            workflow_state: ProjectWorkflowState = "media_ready"
        elif normalized_prompt:
            workflow_state = "awaiting_media"
        else:
            workflow_state = "prompt_input_required"

        project = ProjectModel(
            id=project_id,
            title=title,
            workflow_state=workflow_state,
            created_at=now,
            updated_at=now,
        )
        record = {
            "project": project.model_dump(),
            "edit_draft": edit_draft.model_dump(),
            "chat_turns": [],
            "active_task": None,
            "export_result": None,
            "sequence": 0,
        }
        async with self._lock:
            self._projects[project_id] = record
            self._subscribers.setdefault(project_id, set())
        return record

    def workspace_snapshot(self, project_id: str) -> WorkspaceSnapshotModel:
        record = self.get_project_or_raise(project_id)
        return WorkspaceSnapshotModel.model_validate(
            {
                "project": record["project"],
                "edit_draft": record["edit_draft"],
                "chat_turns": record["chat_turns"],
                "active_task": record["active_task"],
            }
        )

    async def emit(self, project_id: str, event_name: str, data: dict[str, Any]) -> None:
        async with self._lock:
            record = self.get_project_or_raise(project_id)
            record["sequence"] += 1
            envelope = EventEnvelope(
                sequence=record["sequence"],
                event=event_name,
                project_id=project_id,
                emitted_at=_now_iso(),
                data=data,
            ).model_dump()
            subscribers = list(self._subscribers.get(project_id, set()))
        for queue in subscribers:
            await queue.put(envelope)

    def snapshot_event(self, project_id: str) -> dict[str, Any]:
        record = self.get_project_or_raise(project_id)
        return EventEnvelope(
            sequence=record["sequence"],
            event="workspace.snapshot",
            project_id=project_id,
            emitted_at=_now_iso(),
            data={"workspace": self.workspace_snapshot(project_id).model_dump()},
        ).model_dump()

    async def subscribe(self, project_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self.get_project_or_raise(project_id)
            self._subscribers.setdefault(project_id, set()).add(queue)
        return queue

    async def unsubscribe(self, project_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(project_id)
            if subscribers is not None:
                subscribers.discard(queue)

    async def queue_assets_import(self, project_id: str, media: MediaReference) -> TaskModel:
        if not _media_file_refs(media):
            raise CoreApiError(
                status_code=422,
                code="MEDIA_REFERENCE_REQUIRED",
                message="At least one media file or folder_path is required.",
            )

        record = self.get_project_or_raise(project_id)
        now = _now_iso()
        task = TaskModel(
            id=_entity_id("task_ingest"),
            type="ingest",
            status="queued",
            progress=0,
            message="Media ingest queued",
            created_at=now,
            updated_at=now,
        )
        record["active_task"] = task.model_dump()
        record["project"]["workflow_state"] = "media_processing"
        record["project"]["updated_at"] = now
        await self.emit(
            project_id,
            "task.updated",
            {"task": task.model_dump(), "workflow_state": "media_processing"},
        )
        asyncio.create_task(self._run_assets_import(project_id, media, task))
        return task

    async def _run_assets_import(self, project_id: str, media: MediaReference, task: TaskModel) -> None:
        record = self.get_project_or_raise(project_id)
        await asyncio.sleep(0.05)
        running = task.model_copy(
            update={
                "status": "running",
                "progress": 45,
                "message": "Scanning media references",
                "updated_at": _now_iso(),
            }
        )
        record["active_task"] = running.model_dump()
        await self.emit(
            project_id,
            "task.updated",
            {"task": running.model_dump(), "workflow_state": "media_processing"},
        )

        await asyncio.sleep(0.05)
        draft = EditDraftModel.model_validate(record["edit_draft"])
        new_assets = _build_assets(media)
        new_clips = _build_clips(new_assets)
        next_draft = _bump_draft(
            draft,
            assets=[*draft.assets, *new_assets],
            clips=[*draft.clips, *new_clips],
            status="ready" if draft.shots else "draft",
        )
        record["edit_draft"] = next_draft.model_dump()
        record["project"]["workflow_state"] = "ready" if next_draft.shots else "media_ready"
        record["project"]["updated_at"] = next_draft.updated_at
        await self.emit(project_id, "edit_draft.updated", {"edit_draft": next_draft.model_dump()})
        await self.emit(project_id, "project.updated", {"project": record["project"]})

        succeeded = running.model_copy(
            update={
                "status": "succeeded",
                "progress": 100,
                "message": "Media ingest completed",
                "updated_at": _now_iso(),
            }
        )
        record["active_task"] = None
        next_workflow_state: ProjectWorkflowState = "ready" if next_draft.shots else "media_ready"
        record["project"]["workflow_state"] = next_workflow_state
        record["project"]["updated_at"] = _now_iso()
        await self.emit(project_id, "project.updated", {"project": record["project"]})
        await self.emit(
            project_id,
            "task.updated",
            {"task": succeeded.model_dump(), "workflow_state": next_workflow_state},
        )

    async def queue_chat(self, project_id: str, prompt: str, target: ChatTarget | None) -> TaskModel:
        normalized_prompt = _trimmed(prompt)
        if normalized_prompt is None:
            raise CoreApiError(
                status_code=422,
                code="CHAT_PROMPT_REQUIRED",
                message="Prompt is required.",
            )

        record = self.get_project_or_raise(project_id)
        draft = EditDraftModel.model_validate(record["edit_draft"])
        if not draft.assets:
            raise CoreApiError(
                status_code=409,
                code="MEDIA_REQUIRED_FOR_CHAT",
                message="At least one media asset is required before chat can run.",
                details={"project_id": project_id},
            )
        active_task = record["active_task"]
        if active_task and active_task.get("status") in {"queued", "running"}:
            raise CoreApiError(
                status_code=409,
                code="TASK_ALREADY_RUNNING",
                message="Another task is already running for this project.",
                details={"project_id": project_id, "active_task_id": active_task.get("id")},
            )

        now = _now_iso()
        task = TaskModel(
            id=_entity_id("task_chat"),
            type="chat",
            status="queued",
            progress=None,
            message="Chat queued",
            created_at=now,
            updated_at=now,
        )
        user_turn = UserTurnModel(id=_entity_id("turn"), role="user", content=normalized_prompt)
        record["chat_turns"].append(user_turn.model_dump())
        record["active_task"] = task.model_dump()
        record["project"]["workflow_state"] = "chat_thinking"
        record["project"]["updated_at"] = now

        await self.emit(project_id, "chat.turn.created", {"turn": user_turn.model_dump()})
        await self.emit(
            project_id,
            "task.updated",
            {"task": task.model_dump(), "workflow_state": "chat_thinking"},
        )
        asyncio.create_task(self._run_chat(project_id, normalized_prompt, target, task))
        return task

    async def _run_chat(self, project_id: str, prompt: str, target: ChatTarget | None, task: TaskModel) -> None:
        record = self.get_project_or_raise(project_id)
        await asyncio.sleep(0.05)
        running = task.model_copy(
            update={"status": "running", "message": "Analyzing footage and updating edit draft", "updated_at": _now_iso()}
        )
        record["active_task"] = running.model_dump()
        await self.emit(
            project_id,
            "task.updated",
            {"task": running.model_dump(), "workflow_state": "chat_thinking"},
        )

        await asyncio.sleep(0.08)
        draft = EditDraftModel.model_validate(record["edit_draft"])
        shots, scenes = _build_edit_plan(draft.clips, prompt)
        scoped_target = "selected scene" if target and target.scene_id else "whole draft"
        next_draft = _bump_draft(
            draft,
            shots=shots,
            scenes=scenes,
            selected_scene_id=scenes[0].id if scenes else None,
            selected_shot_id=shots[0].id if shots else None,
            status="ready",
        )
        assistant_turn = AssistantDecisionTurnModel(
            id=_entity_id("turn"),
            role="assistant",
            type="decision",
            decision_type="EDIT_DRAFT_PATCH",
            reasoning_summary=f"Refocused the cut around {scoped_target}: {prompt[:80]}",
            ops=[
                AssistantDecisionOperationModel(
                    id=_entity_id("op"),
                    action="replace_edit_draft_structure",
                    target="workspace.edit_draft",
                    summary="Generated a new shot sequence and optional scene grouping from current clips.",
                ),
                AssistantDecisionOperationModel(
                    id=_entity_id("op"),
                    action="select_edit_target",
                    target="workspace.edit_draft.selected_scene_id",
                    summary="Moved the active focus to the primary scene of the new draft.",
                ),
            ],
        )
        record["edit_draft"] = next_draft.model_dump()
        record["chat_turns"].append(assistant_turn.model_dump())
        record["project"]["workflow_state"] = "ready"
        record["project"]["updated_at"] = next_draft.updated_at
        record["active_task"] = None

        await self.emit(project_id, "chat.turn.created", {"turn": assistant_turn.model_dump()})
        await self.emit(project_id, "edit_draft.updated", {"edit_draft": next_draft.model_dump()})
        await self.emit(project_id, "project.updated", {"project": record["project"]})

        succeeded = running.model_copy(update={"status": "succeeded", "message": "Chat completed", "updated_at": _now_iso()})
        await self.emit(
            project_id,
            "task.updated",
            {"task": succeeded.model_dump(), "workflow_state": "ready"},
        )

    async def queue_export(self, project_id: str, payload: ExportRequest) -> TaskModel:
        record = self.get_project_or_raise(project_id)
        draft = EditDraftModel.model_validate(record["edit_draft"])
        if not draft.shots:
            raise CoreApiError(
                status_code=409,
                code="EDIT_DRAFT_REQUIRED",
                message="Edit draft with at least one shot is required before export can run.",
                details={"project_id": project_id},
            )
        active_task = record["active_task"]
        if active_task and active_task.get("status") in {"queued", "running"}:
            raise CoreApiError(
                status_code=409,
                code="TASK_ALREADY_RUNNING",
                message="Another task is already running for this project.",
                details={"project_id": project_id, "active_task_id": active_task.get("id")},
            )

        now = _now_iso()
        task = TaskModel(
            id=_entity_id("task_render"),
            type="render",
            status="queued",
            progress=0,
            message="Export queued",
            created_at=now,
            updated_at=now,
        )
        record["active_task"] = task.model_dump()
        record["project"]["workflow_state"] = "rendering"
        record["project"]["updated_at"] = now
        record["edit_draft"] = _bump_draft(draft, status="rendering", updated_at=now).model_dump()
        await self.emit(
            project_id,
            "task.updated",
            {"task": task.model_dump(), "workflow_state": "rendering"},
        )
        asyncio.create_task(self._run_export(project_id, payload, task))
        return task

    async def _run_export(self, project_id: str, payload: ExportRequest, task: TaskModel) -> None:
        record = self.get_project_or_raise(project_id)
        await asyncio.sleep(0.05)
        running = task.model_copy(update={"status": "running", "progress": 50, "message": "Rendering draft export", "updated_at": _now_iso()})
        record["active_task"] = running.model_dump()
        await self.emit(
            project_id,
            "task.updated",
            {"task": running.model_dump(), "workflow_state": "rendering"},
        )

        await asyncio.sleep(0.08)
        result = {
            "render_type": "export",
            "output_url": f"file:///tmp/{project_id}_draft.{payload.format or 'mp4'}",
            "duration_ms": 4800,
            "file_size_bytes": 18_000_000,
            "thumbnail_url": None,
            "format": payload.format or "mp4",
            "quality": payload.quality,
            "resolution": "1920x1080",
        }
        draft = EditDraftModel.model_validate(record["edit_draft"])
        ready_draft = _bump_draft(draft, status="ready")
        record["export_result"] = result
        record["edit_draft"] = ready_draft.model_dump()
        record["active_task"] = None
        record["project"]["workflow_state"] = "ready"
        record["project"]["updated_at"] = ready_draft.updated_at

        await self.emit(project_id, "edit_draft.updated", {"edit_draft": ready_draft.model_dump()})
        await self.emit(project_id, "export.completed", {"result": result})
        await self.emit(project_id, "project.updated", {"project": record["project"]})
        succeeded = running.model_copy(update={"status": "succeeded", "progress": 100, "message": "Export completed", "updated_at": _now_iso()})
        await self.emit(
            project_id,
            "task.updated",
            {"task": succeeded.model_dump(), "workflow_state": "ready"},
        )


store = InMemoryProjectStore()


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "").strip() or _request_id()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(CoreApiError)
async def core_api_error_handler(request: Request, exc: CoreApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorEnvelope(
            error=ErrorBody(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                request_id=getattr(request.state, "request_id", None),
            )
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ErrorEnvelope(
            error=ErrorBody(
                code="CORE_IN_MEMORY_UNHANDLED",
                message=str(exc) or "Unhandled in-memory core error.",
                details={"phase": REWRITE_PHASE},
                request_id=getattr(request.state, "request_id", None),
            )
        ).model_dump(),
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "core",
        "version": APP_VERSION,
        "phase": REWRITE_PHASE,
        "mode": CORE_MODE,
        "timestamp": _now_iso(),
        "notes": [
            "Legacy business logic has been removed.",
            "This service now runs an in-memory EditDraft contract for Launchpad and Workspace.",
        ],
    }


@app.get("/api/v1/runtime/capabilities", response_model=RuntimeCapabilitiesResponse)
def runtime_capabilities() -> RuntimeCapabilitiesResponse:
    return RuntimeCapabilitiesResponse(
        service="core",
        version=APP_VERSION,
        phase=REWRITE_PHASE,
        mode=CORE_MODE,
        retained_surfaces=[
            "health",
            "projects",
            "project_snapshot",
            "project_events",
            "chat",
            "asset_import",
            "export",
            "request_id_middleware",
            "cors_for_local_client",
        ],
    )


@app.get("/api/v1/projects", response_model=ListProjectsResponse)
async def list_projects(limit: int = Query(default=20, ge=1, le=100)) -> ListProjectsResponse:
    return ListProjectsResponse(projects=store.list_projects(limit))


@app.post("/api/v1/projects", response_model=CreateProjectResponse)
async def create_project(payload: CreateProjectRequest) -> CreateProjectResponse:
    record = await store.create_project(payload)
    workspace = store.workspace_snapshot(record["project"]["id"])
    return CreateProjectResponse(project=ProjectModel.model_validate(record["project"]), workspace=workspace)


@app.get("/api/v1/projects/{project_id}", response_model=GetWorkspaceResponse)
async def get_project(project_id: str) -> GetWorkspaceResponse:
    return GetWorkspaceResponse(workspace=store.workspace_snapshot(project_id))


@app.post("/api/v1/projects/{project_id}/assets:import", response_model=TaskResponse)
async def import_assets(project_id: str, payload: ImportAssetsRequest) -> TaskResponse:
    task = await store.queue_assets_import(project_id, payload.media)
    return TaskResponse(task=task)


@app.post("/api/v1/projects/{project_id}/chat", response_model=TaskResponse)
async def chat(project_id: str, payload: ChatRequest) -> TaskResponse:
    task = await store.queue_chat(project_id, payload.prompt, payload.target)
    return TaskResponse(task=task)


@app.post("/api/v1/projects/{project_id}/export", response_model=TaskResponse)
async def export_project(project_id: str, payload: ExportRequest) -> TaskResponse:
    task = await store.queue_export(project_id, payload)
    return TaskResponse(task=task)


@app.websocket("/api/v1/projects/{project_id}/events")
async def project_events(websocket: WebSocket, project_id: str) -> None:
    try:
        store.get_project_or_raise(project_id)
    except CoreApiError:
        await websocket.close(code=4404, reason="Project not found")
        return

    await websocket.accept()
    queue = await store.subscribe(project_id)
    try:
        await websocket.send_json(store.snapshot_event(project_id))
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
    finally:
        await store.unsubscribe(project_id, queue)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "core",
        "phase": REWRITE_PHASE,
        "mode": CORE_MODE,
        "message": "EntroCut core serves an in-memory EditDraft contract for Launchpad, Workspace, chat, and project events.",
        "env": {
            "core_db_path": os.getenv("CORE_DB_PATH", "not_configured"),
            "server_base_url": os.getenv("SERVER_BASE_URL", "http://127.0.0.1:8001"),
        },
    }
