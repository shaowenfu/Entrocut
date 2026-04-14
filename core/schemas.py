from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ProjectLifecycleState = Literal["active", "archived"]
AssetProcessingStage = Literal["pending", "segmenting", "vectorizing", "ready", "failed"]
AssetType = Literal["video", "audio"]
TaskSlot = Literal["media", "agent", "export"]
TaskType = Literal["ingest", "index", "chat", "render"]
TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
EditDraftStatus = Literal["draft", "ready", "rendering", "failed"]
LockedShotField = Literal["source_range", "order", "clip_id", "enabled"]
LockedSceneField = Literal["shot_ids", "order", "enabled", "intent"]
DecisionType = Literal["EDIT_DRAFT_PATCH"]
PlannerDecisionStatus = Literal["final", "requires_tool"]
PlannerDraftStrategy = Literal["placeholder_first_cut", "no_change"]
ToolName = Literal["read", "retrieve", "inspect", "patch", "preview"]
ChatMode = Literal["planning_only", "editing"]
ProjectSummaryState = Literal["blank", "planning", "media_processing", "editing", "exporting", "attention_required"]
ConversationFeedbackState = Literal["unknown", "clarify", "approve", "reject", "revise"]
ExecutionAgentRunState = Literal["idle", "planning", "executing_tool", "waiting_user", "failed"]
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

    @field_validator("path")
    @classmethod
    def validate_absolute_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not Path(normalized).is_absolute():
            raise ValueError("media file path must be an absolute local path")
        return normalized


class MediaReference(BaseModel):
    folder_path: str | None = None
    files: list[MediaFileReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_fields(self) -> "MediaReference":
        if self.folder_path and self.files:
            raise ValueError("media reference cannot include both folder_path and files")
        return self


class ProjectModel(BaseModel):
    id: str
    title: str
    summary_state: ProjectSummaryState | None = None
    lifecycle_state: ProjectLifecycleState = "active"
    created_at: str
    updated_at: str


class AssetProcessingState(BaseModel):
    stage: AssetProcessingStage = "pending"
    progress: int | None = None
    clip_count: int = 0
    indexed_clip_count: int = 0
    last_error: dict[str, Any] | None = None
    updated_at: str | None = None


class AssetModel(BaseModel):
    id: str
    name: str
    duration_ms: int
    type: AssetType
    source_path: str | None = None
    processing_stage: AssetProcessingStage = "pending"
    processing_progress: int | None = None
    clip_count: int = 0
    indexed_clip_count: int = 0
    last_error: dict[str, Any] | None = None
    updated_at: str | None = None


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


class ProjectMediaSummary(BaseModel):
    asset_count: int = 0
    pending_asset_count: int = 0
    processing_asset_count: int = 0
    ready_asset_count: int = 0
    failed_asset_count: int = 0
    total_clip_count: int = 0
    indexed_clip_count: int = 0
    retrieval_ready: bool = False


class GoalState(BaseModel):
    brief: str | None = None
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class FocusState(BaseModel):
    scope_type: Literal["project", "scene", "shot"] = "project"
    scene_id: str | None = None
    shot_id: str | None = None
    updated_at: str | None = None


class ConversationState(BaseModel):
    pending_questions: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    latest_user_feedback: ConversationFeedbackState = "unknown"
    updated_at: str | None = None


class RetrievalState(BaseModel):
    last_query: str | None = None
    candidate_clip_ids: list[str] = Field(default_factory=list)
    retrieval_ready: bool = False
    blocking_reason: str | None = None
    updated_at: str | None = None


class ExecutionState(BaseModel):
    agent_run_state: ExecutionAgentRunState = "idle"
    current_task_id: str | None = None
    last_tool_name: str | None = None
    last_error: dict[str, Any] | None = None
    updated_at: str | None = None


class ProjectRuntimeState(BaseModel):
    goal_state: GoalState = Field(default_factory=GoalState)
    focus_state: FocusState = Field(default_factory=FocusState)
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    retrieval_state: RetrievalState = Field(default_factory=RetrievalState)
    execution_state: ExecutionState = Field(default_factory=ExecutionState)
    updated_at: str | None = None


class ProjectCapabilities(BaseModel):
    can_send_chat: bool = False
    chat_mode: ChatMode = "planning_only"
    can_retrieve: bool = False
    can_inspect: bool = False
    can_patch_draft: bool = False
    can_preview: bool = False
    can_export: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)


class TaskModel(BaseModel):
    id: str
    slot: TaskSlot = "agent"
    type: TaskType
    status: TaskStatus
    owner_type: Literal["project", "asset", "draft"] = "project"
    owner_id: str | None = None
    progress: int | None = None
    message: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class WorkspaceSnapshotModel(BaseModel):
    project: ProjectModel
    edit_draft: EditDraftModel
    chat_turns: list[ChatTurnModel]
    summary_state: ProjectSummaryState | None = None
    media_summary: ProjectMediaSummary = Field(default_factory=ProjectMediaSummary)
    runtime_state: ProjectRuntimeState = Field(default_factory=ProjectRuntimeState)
    capabilities: ProjectCapabilities = Field(default_factory=ProjectCapabilities)
    active_tasks: list[TaskModel] = Field(default_factory=list)
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
    runtime_state: ProjectRuntimeState = Field(default_factory=ProjectRuntimeState)


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
