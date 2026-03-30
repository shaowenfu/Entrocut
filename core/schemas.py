from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

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
PlannerDecisionStatus = Literal["final", "requires_tool"]
PlannerDraftStrategy = Literal["placeholder_first_cut", "no_change"]
ToolName = Literal["read", "retrieve", "inspect", "patch", "preview"]
SUPPORTED_TOOL_NAMES: set[str] = {"read", "retrieve", "inspect", "patch", "preview"}


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


class PlannerDecisionModel(BaseModel):
    status: PlannerDecisionStatus
    reasoning_summary: str
    assistant_reply: str
    tool_name: str | None = None
    tool_input_summary: str | None = None
    draft_strategy: PlannerDraftStrategy = "placeholder_first_cut"


class ToolCallModel(BaseModel):
    tool_name: ToolName
    tool_input: dict[str, Any] = Field(default_factory=dict)


class ToolObservationModel(BaseModel):
    tool_name: ToolName
    success: bool
    summary: str
    output: dict[str, Any] = Field(default_factory=dict)
    state_delta: dict[str, Any] = Field(default_factory=dict)


class AgentLoopResultModel(BaseModel):
    final_decision: PlannerDecisionModel
    draft: EditDraftModel
    observations: list[ToolObservationModel] = Field(default_factory=list)


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
