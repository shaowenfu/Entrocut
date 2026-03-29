from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

APP_VERSION = "0.8.0-edit-draft"
REWRITE_PHASE = "clean_room_rewrite"
CORE_MODE = "prototype_backed"
DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:8001"
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", DEFAULT_SERVER_BASE_URL).rstrip("/")
SERVER_CHAT_MODEL = os.getenv("SERVER_CHAT_MODEL", "entro-reasoning-v1").strip() or "entro-reasoning-v1"
SERVER_CHAT_TIMEOUT_SECONDS = float(os.getenv("SERVER_CHAT_TIMEOUT_SECONDS", "30"))
AGENT_LOOP_MAX_ITERATIONS = int(os.getenv("AGENT_LOOP_MAX_ITERATIONS", "3"))
DEFAULT_BYOK_BASE_URL = "https://api.openai.com"

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


class CoreAuthSessionRequest(BaseModel):
    access_token: str = Field(min_length=16)
    user_id: str | None = None


class CoreAuthSessionResponse(BaseModel):
    status: str = "ok"
    user_id: str | None = None


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
    model: str | None = None


PlannerDecisionStatus = Literal["final", "requires_tool"]
PlannerDraftStrategy = Literal["placeholder_first_cut", "no_change"]


class PlannerDecisionModel(BaseModel):
    status: PlannerDecisionStatus
    reasoning_summary: str
    assistant_reply: str
    tool_name: str | None = None
    tool_input_summary: str | None = None
    draft_strategy: PlannerDraftStrategy = "placeholder_first_cut"


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


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"].strip())
        return " ".join(part for part in parts if part)
    return ""


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


def _draft_summary(draft: EditDraftModel) -> dict[str, Any]:
    return {
        "draft_id": draft.id,
        "draft_version": draft.version,
        "asset_count": len(draft.assets),
        "clip_count": len(draft.clips),
        "shot_count": len(draft.shots),
        "scene_count": len(draft.scenes or []),
        "selected_scene_id": draft.selected_scene_id,
        "selected_shot_id": draft.selected_shot_id,
        "clip_excerpt": [
            {
                "clip_id": clip.id,
                "asset_id": clip.asset_id,
                "visual_desc": clip.visual_desc,
                "semantic_tags": clip.semantic_tags,
            }
            for clip in draft.clips[:6]
        ],
    }


def _chat_history_summary(record: dict[str, Any], *, max_turns: int = 6) -> list[str]:
    lines: list[str] = []
    for turn in record["chat_turns"][-max_turns:]:
        if turn.get("role") == "user":
            lines.append(f"user: {str(turn.get('content', '')).strip()[:160]}")
            continue
        if turn.get("role") == "assistant":
            lines.append(f"assistant: {str(turn.get('reasoning_summary', '')).strip()[:160]}")
    return lines


def _extract_first_json_object(text: str) -> str | None:
    depth = 0
    start_index: int | None = None
    for index, char in enumerate(text):
        if char == "{":
            if start_index is None:
                start_index = index
            depth += 1
        elif char == "}":
            if start_index is None:
                continue
            depth -= 1
            if depth == 0:
                return text[start_index : index + 1]
    return None


async def _emit_agent_progress(
    project_id: str,
    *,
    phase: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> None:
    await store.emit(
        project_id,
        "agent.step.updated",
        {
            "phase": phase,
            "summary": summary,
            "details": details or {},
        },
    )


def _build_planner_messages(
    *,
    record: dict[str, Any],
    project_id: str,
    prompt: str,
    draft: EditDraftModel,
    target: ChatTarget | None,
    iteration: int,
) -> list[dict[str, Any]]:
    planner_context = {
        "project_id": project_id,
        "iteration": iteration,
        "user_input": prompt,
        "target": target.model_dump() if target else None,
        "workspace_snapshot": {
            "project": record["project"],
            "draft": _draft_summary(draft),
        },
        "chat_history_summary": _chat_history_summary(record),
        "prototype_constraints": {
            "planner_loop": "implemented",
            "tool_execution": "todo_not_implemented",
            "allowed_draft_strategy": ["placeholder_first_cut", "no_change"],
        },
    }
    system_prompt = (
        "You are the planning layer for EntroCut Core.\n"
        "Decide the next agent step using the provided context.\n"
        "Return exactly one JSON object with these fields:\n"
        "- status: \"final\" | \"requires_tool\"\n"
        "- reasoning_summary: short English planning summary\n"
        "- assistant_reply: concise Chinese reply for the user\n"
        "- tool_name: string or null\n"
        "- tool_input_summary: string or null\n"
        "- draft_strategy: \"placeholder_first_cut\" | \"no_change\"\n"
        "Current prototype rule: tool execution is not implemented yet, so prefer status=\"final\" unless a tool is truly mandatory.\n"
        "Do not return markdown, code fences, or extra prose."
    )
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(planner_context, ensure_ascii=False),
        },
    ]


async def _request_server_planner_decision(
    *,
    access_token: str,
    record: dict[str, Any],
    project_id: str,
    prompt: str,
    draft: EditDraftModel,
    target: ChatTarget | None,
    iteration: int,
) -> PlannerDecisionModel:
    payload = {
        "model": SERVER_CHAT_MODEL,
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 600,
        "messages": _build_planner_messages(
            record=record,
            project_id=project_id,
            prompt=prompt,
            draft=draft,
            target=target,
            iteration=iteration,
        ),
    }

    async with httpx.AsyncClient(timeout=SERVER_CHAT_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{SERVER_BASE_URL}/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Request-ID": _request_id(),
            },
        )

    if response.status_code == 401:
        raise CoreApiError(
            status_code=401,
            code="AUTH_SESSION_EXPIRED",
            message="Core auth session is expired. Refresh login in client and resync token.",
            details={"server_status": 401},
        )
    if response.status_code == 403:
        raise CoreApiError(
            status_code=403,
            code="AUTH_SESSION_FORBIDDEN",
            message="The current user is not allowed to call server planner proxy.",
            details={"server_status": 403},
        )
    if response.status_code >= 400:
        details: dict[str, Any] = {"server_status": response.status_code}
        try:
            body = response.json()
            if isinstance(body, dict):
                details["server_error"] = body
        except Exception:
            details["server_error_text"] = response.text[:400]
        raise CoreApiError(
            status_code=502,
            code="SERVER_PLANNER_PROXY_FAILED",
            message="Server planner proxy rejected the request.",
            details=details,
        )

    body = response.json()
    choices = body.get("choices") if isinstance(body, dict) else None
    message = choices[0].get("message") if isinstance(choices, list) and choices else None
    content = _extract_text_content(message.get("content") if isinstance(message, dict) else None)
    if not content:
        raise CoreApiError(
            status_code=502,
            code="SERVER_PLANNER_PROXY_EMPTY",
            message="Server planner proxy returned an empty assistant message.",
        )
    json_payload = _extract_first_json_object(content)
    if not json_payload:
        raise CoreApiError(
            status_code=502,
            code="PLANNER_DECISION_INVALID",
            message="Planner response did not contain a JSON decision object.",
            details={"raw_content": content[:400]},
        )
    try:
        parsed = json.loads(json_payload)
    except json.JSONDecodeError as exc:
        raise CoreApiError(
            status_code=502,
            code="PLANNER_DECISION_INVALID",
            message="Planner response returned malformed JSON.",
            details={"raw_content": json_payload[:400]},
        ) from exc
    try:
        return PlannerDecisionModel.model_validate(parsed)
    except ValidationError as exc:
        raise CoreApiError(
            status_code=502,
            code="PLANNER_DECISION_INVALID",
            message="Planner response failed schema validation.",
            details={"validation_errors": exc.errors()},
        ) from exc


async def _run_chat_agent_loop(
    *,
    record: dict[str, Any],
    project_id: str,
    access_token: str,
    prompt: str,
    draft: EditDraftModel,
    target: ChatTarget | None,
) -> PlannerDecisionModel:
    await _emit_agent_progress(
        project_id,
        phase="loop_started",
        summary="Agent loop started.",
        details={"max_iterations": AGENT_LOOP_MAX_ITERATIONS},
    )
    current_draft = draft
    for iteration in range(1, AGENT_LOOP_MAX_ITERATIONS + 1):
        await _emit_agent_progress(
            project_id,
            phase="planner_context_assembled",
            summary="Planner context assembled.",
            details={"iteration": iteration, "draft_version": current_draft.version},
        )
        decision = await _request_server_planner_decision(
            access_token=access_token,
            record=record,
            project_id=project_id,
            prompt=prompt,
            draft=current_draft,
            target=target,
            iteration=iteration,
        )
        await _emit_agent_progress(
            project_id,
            phase="planner_decision_received",
            summary="Planner decision received.",
            details={
                "iteration": iteration,
                "status": decision.status,
                "draft_strategy": decision.draft_strategy,
                "tool_name": decision.tool_name,
            },
        )
        if decision.status == "requires_tool":
            await _emit_agent_progress(
                project_id,
                phase="tool_execution_todo",
                summary="Planner requested tool execution, but the execution loop is still TODO.",
                details={
                    "iteration": iteration,
                    "tool_name": decision.tool_name,
                    "tool_input_summary": decision.tool_input_summary,
                },
            )
            raise CoreApiError(
                status_code=501,
                code="AGENT_TOOL_EXECUTION_TODO",
                message="Planner requested tool execution, but tool execution loop is not implemented in Core yet.",
                details={
                    "iteration": iteration,
                    "tool_name": decision.tool_name,
                    "tool_input_summary": decision.tool_input_summary,
                },
            )
        return decision
    raise CoreApiError(
        status_code=502,
        code="AGENT_LOOP_DID_NOT_FINALIZE",
        message="Planner loop exceeded the iteration budget without producing a final decision.",
        details={"max_iterations": AGENT_LOOP_MAX_ITERATIONS},
    )


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

    async def queue_chat(self, project_id: str, prompt: str, target: ChatTarget | None, model: str | None, routing_mode: str, byok_key: str | None, byok_base_url: str | None) -> TaskModel:
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
        asyncio.create_task(self._run_chat(project_id, normalized_prompt, target, task, model, routing_mode, byok_key, byok_base_url))
        return task

    async def _run_chat(self, project_id: str, prompt: str, target: ChatTarget | None, task: TaskModel, model: str | None, routing_mode: str, byok_key: str | None, byok_base_url: str | None) -> None:
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

        try:
            await asyncio.sleep(0.08)
            draft = EditDraftModel.model_validate(record["edit_draft"])
            auth_session = await auth_session_store.snapshot()
            access_token = auth_session.get("access_token")
            if not access_token:
                raise CoreApiError(
                    status_code=401,
                    code="AUTH_SESSION_REQUIRED",
                    message="Sign in is required before chat can run.",
                )
            decision = await _run_chat_agent_loop(
                record=record,
                access_token=access_token,
                project_id=project_id,
                prompt=prompt,
                draft=draft,
                target=target,
                model=model,
                routing_mode=routing_mode,
                byok_key=byok_key,
                byok_base_url=byok_base_url,
            )
            if decision.draft_strategy == "placeholder_first_cut":
                shots, scenes = _build_edit_plan(draft.clips, prompt)
            else:
                shots = list(draft.shots)
                scenes = list(draft.scenes or [])
            next_draft = _bump_draft(
                draft,
                shots=shots,
                scenes=scenes,
                selected_scene_id=scenes[0].id if scenes else draft.selected_scene_id,
                selected_shot_id=shots[0].id if shots else draft.selected_shot_id,
                status="ready",
            )
            reply_text = decision.assistant_reply.strip() or decision.reasoning_summary.strip()
            ops = [
                AssistantDecisionOperationModel(
                    id=_entity_id("op"),
                    action="planner_context_assembled",
                    target="core.agent.loop",
                    summary="Built planner context from workspace snapshot, chat summary, target scope, and user input.",
                ),
                AssistantDecisionOperationModel(
                    id=_entity_id("op"),
                    action="planner_decision_finalized",
                    target="server.v1.chat.completions",
                    summary=f"Planner returned a final decision with draft strategy {decision.draft_strategy}.",
                ),
                AssistantDecisionOperationModel(
                    id=_entity_id("op"),
                    action="todo_tool_execution_loop",
                    target="core.agent.tools",
                    summary="Tool execution remains TODO in the current prototype; planner-driven loop shape is preserved.",
                ),
            ]
            if decision.draft_strategy == "placeholder_first_cut":
                ops.append(
                    AssistantDecisionOperationModel(
                        id=_entity_id("op"),
                        action="placeholder_edit_draft_applied",
                        target="workspace.edit_draft",
                        summary="Applied the current placeholder first-cut strategy while planner-driven tools are still TODO.",
                    )
                )
            else:
                ops.append(
                    AssistantDecisionOperationModel(
                        id=_entity_id("op"),
                        action="no_edit_draft_change",
                        target="workspace.edit_draft",
                        summary="Planner explicitly chose not to modify the draft in the current iteration.",
                    )
                )
            assistant_turn = AssistantDecisionTurnModel(
                id=_entity_id("turn"),
                role="assistant",
                type="decision",
                decision_type="EDIT_DRAFT_PATCH",
                reasoning_summary=reply_text,
                ops=ops,
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
        except CoreApiError as exc:
            await _mark_chat_failed(
                project_id=project_id,
                task=running,
                message=exc.message,
                code=exc.code,
                details=exc.details,
            )
        except Exception as exc:
            await _mark_chat_failed(
                project_id=project_id,
                task=running,
                message="Chat orchestration failed unexpectedly.",
                code="CHAT_ORCHESTRATION_FAILED",
                details={"cause": str(exc)},
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


class CoreAuthSessionStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._session: dict[str, str | None] = {
            "access_token": None,
            "user_id": None,
        }

    async def set_session(self, access_token: str, user_id: str | None) -> None:
        async with self._lock:
            self._session = {
                "access_token": access_token.strip(),
                "user_id": user_id.strip() if user_id and user_id.strip() else None,
            }

    async def clear_session(self) -> None:
        async with self._lock:
            self._session = {"access_token": None, "user_id": None}

    async def snapshot(self) -> dict[str, str | None]:
        async with self._lock:
            return dict(self._session)

async def _request_server_chat_completion(
    *,
    access_token: str,
    project_id: str,
    prompt: str,
    draft: EditDraftModel,
    target: ChatTarget | None,
    model: str | None,
    routing_mode: str,
    byok_key: str | None,
    byok_base_url: str | None,
) -> dict[str, Any]:
    clip_context = [
        {
            "clip_id": clip.id,
            "asset_id": clip.asset_id,
            "visual_desc": clip.visual_desc,
            "semantic_tags": clip.semantic_tags,
        }
        for clip in draft.clips[:6]
    ]
    system_context = {
        "project_id": project_id,
        "asset_count": len(draft.assets),
        "clip_count": len(draft.clips),
        "selected_scene_id": target.scene_id if target else None,
        "selected_shot_id": target.shot_id if target else None,
        "clips": clip_context,
    }
    payload = {
        "model": model.strip() if isinstance(model, str) and model.strip() else SERVER_CHAT_MODEL,
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 400,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the editing reasoning layer for EntroCut Core. "
                    "Summarize the editing intent in concise English, referencing the available footage context. "
                    f"Context: {system_context}"
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    }

    request_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Request-ID": _request_id(),
    }
    if routing_mode == "BYOK":
        normalized_key = (byok_key or "").strip()
        if not normalized_key:
            raise CoreApiError(
                status_code=422,
                code="BYOK_KEY_REQUIRED",
                message="X-BYOK-Key is required when X-Routing-Mode is BYOK.",
            )
        base_url = (byok_base_url or DEFAULT_BYOK_BASE_URL).rstrip("/")
        endpoint_url = f"{base_url}/v1/chat/completions"
        request_headers["Authorization"] = f"Bearer {normalized_key}"
    else:
        endpoint_url = f"{SERVER_BASE_URL}/v1/chat/completions"
        request_headers["Authorization"] = f"Bearer {access_token}"

    async with httpx.AsyncClient(timeout=SERVER_CHAT_TIMEOUT_SECONDS) as client:
        response = await client.post(endpoint_url, json=payload, headers=request_headers)

    if response.status_code == 401:
        raise CoreApiError(
            status_code=401,
            code="AUTH_SESSION_EXPIRED",
            message="Core auth session is expired. Refresh login in client and resync token.",
            details={"server_status": 401},
        )
    if response.status_code == 403:
        raise CoreApiError(
            status_code=403,
            code="AUTH_SESSION_FORBIDDEN",
            message="The current user is not allowed to call server chat proxy.",
            details={"server_status": 403},
        )
    if response.status_code >= 400:
        details: dict[str, Any] = {"server_status": response.status_code}
        try:
            body = response.json()
            if isinstance(body, dict):
                details["server_error"] = body
        except Exception:
            details["server_error_text"] = response.text[:400]
        raise CoreApiError(
            status_code=502,
            code="SERVER_CHAT_PROXY_FAILED",
            message="Server chat proxy rejected the request.",
            details=details,
        )

    body = response.json()
    choices = body.get("choices") if isinstance(body, dict) else None
    message = choices[0].get("message") if isinstance(choices, list) and choices else None
    content = _extract_text_content(message.get("content") if isinstance(message, dict) else None)
    if not content:
        raise CoreApiError(
            status_code=502,
            code="SERVER_CHAT_PROXY_EMPTY",
            message="Server chat proxy returned an empty assistant message.",
        )
    return {
        "content": content,
        "usage": body.get("usage") if isinstance(body, dict) else None,
        "entro_metadata": body.get("entro_metadata") if isinstance(body, dict) else None,
    }
async def _mark_chat_failed(
    *,
    project_id: str,
    task: TaskModel,
    message: str,
    code: str,
    details: dict[str, Any] | None = None,
) -> None:
    record = store.get_project_or_raise(project_id)
    draft = EditDraftModel.model_validate(record["edit_draft"])
    workflow_state: ProjectWorkflowState = "ready" if draft.shots else "media_ready"
    failed_task = task.model_copy(
        update={
            "status": "failed",
            "message": message,
            "updated_at": _now_iso(),
        }
    )
    record["active_task"] = None
    record["project"]["workflow_state"] = workflow_state
    record["project"]["updated_at"] = _now_iso()
    await store.emit(
        project_id,
        "error.occurred",
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
            "workflow_state": workflow_state,
        },
    )
    await store.emit(project_id, "project.updated", {"project": record["project"]})
    await store.emit(
        project_id,
        "task.updated",
        {"task": failed_task.model_dump(), "workflow_state": workflow_state},
    )


store = InMemoryProjectStore()
auth_session_store = CoreAuthSessionStore()


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
            "auth_session",
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
async def chat(project_id: str, payload: ChatRequest, request: Request) -> TaskResponse:
    auth_session = await auth_session_store.snapshot()
    if not auth_session.get("access_token"):
        raise CoreApiError(
            status_code=401,
            code="AUTH_SESSION_REQUIRED",
            message="Sign in is required before chat can run.",
        )
    routing_mode = (request.headers.get("X-Routing-Mode") or "Platform").strip()
    normalized_mode = "BYOK" if routing_mode.upper() == "BYOK" else "Platform"
    task = await store.queue_chat(
        project_id,
        payload.prompt,
        payload.target,
        payload.model,
        normalized_mode,
        request.headers.get("X-BYOK-Key"),
        request.headers.get("X-BYOK-BaseURL"),
    )
    return TaskResponse(task=task)


@app.post("/api/v1/auth/session", response_model=CoreAuthSessionResponse)
async def set_auth_session(payload: CoreAuthSessionRequest) -> CoreAuthSessionResponse:
    await auth_session_store.set_session(payload.access_token, payload.user_id)
    return CoreAuthSessionResponse(user_id=payload.user_id)


@app.delete("/api/v1/auth/session", response_model=CoreAuthSessionResponse)
async def clear_auth_session() -> CoreAuthSessionResponse:
    await auth_session_store.clear_session()
    return CoreAuthSessionResponse(user_id=None)


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
            "server_base_url": SERVER_BASE_URL,
        },
    }
