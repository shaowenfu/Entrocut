import { create } from "zustand";
import {
  assembleActionContext,
  type ContextAssemblyResult,
} from "../agent/contextAssembler";
import { runExecutionLoop, type RunExecutionLoopResult } from "../agent/executionLoop";
import { createLlmPlannerRunner } from "../agent/llmPlannerRunner";
import { createHeuristicPlannerRunner } from "../agent/plannerRunner";
import { createLocalToolExecutor } from "../agent/toolExecutor";
import {
  createEmptySessionRuntimeState,
  type PlannerActionType,
  recordExecutionAction,
  syncRuntimeStateFromWorkspace,
  updateSelectionState,
  type RuntimeScope,
  type SessionRuntimeState,
} from "../agent/sessionRuntimeState";
import { normalizeMediaInput, pickMediaFromSystem, type MediaPickInput } from "../services/electronBridge";
import {
  createProjectEventsSocket,
  exportProject as exportProjectRequest,
  getWorkspace,
  importAssets as importAssetsRequest,
  sendChat as sendChatRequest,
  toMediaReference,
  toRequestError,
  type CoreChatAssistantTurn,
  type CoreChatTurn,
  type CoreEditDraft,
  type CoreEventEnvelope,
  type CoreExportResult,
  type CoreProject,
  type CoreShot,
  type CoreTask,
  type CoreWorkspaceSnapshot,
  type ProjectWorkflowState,
  type TaskStatus,
  type TaskType,
} from "../services/coreClient";
import { registerProjectMediaSources } from "../services/localMediaRegistry";

export interface WorkspaceAssetItem {
  id: string;
  name: string;
  duration: string;
  type: "video" | "audio";
  sourcePath?: string | null;
}

export interface WorkspaceClipItem {
  id: string;
  parent: string;
  start: string;
  end: string;
  score: string;
  desc: string;
  thumbClass: string;
}

export interface StoryboardScene {
  id: string;
  title: string;
  duration: string;
  intent: string;
  colorClass: string;
  bgClass: string;
  shotIds: string[];
  primaryClipId: string | null;
}

export interface UserTurn {
  id: string;
  role: "user";
  content: string;
}

export interface AssistantDecisionOperation {
  id: string;
  action: string;
  target: string;
  summary: string;
}

export interface AssistantDecisionTurn {
  id: string;
  role: "assistant";
  type: "decision";
  decision_type: string;
  reasoning_summary: string;
  ops: AssistantDecisionOperation[];
}

export type ChatTurn = UserTurn | AssistantDecisionTurn;

type ProcessingPhase = "idle" | "media_processing" | "indexing" | "chat_thinking" | "ready" | "failed";
type WorkflowState = ProjectWorkflowState;
type WorkspaceLoadState = "idle" | "loading" | "ready" | "failed";
type ChatState = "idle" | "responding" | "failed";
type EventStreamState = "disconnected" | "connecting" | "connected";
type ReconnectState = "idle" | "reconnecting" | "max_attempts_reached";

interface WorkspaceError {
  code: string;
  message: string;
  cause?: string;
  requestId?: string;
}

interface BootstrapInput {
  projectId: string;
  workspaceName: string;
  prompt?: string;
  hasMedia: boolean;
}

interface UploadAssetsInput extends MediaPickInput {
  shouldPickMedia?: boolean;
}

interface ExportResult extends CoreExportResult {}

interface ActiveTask {
  id: string;
  type: TaskType;
  status: TaskStatus;
  progress?: number | null;
  message?: string | null;
}

type WorkspaceEvent =
  | { type: "WORKSPACE_LOAD_STARTED"; workspaceId: string; workspaceName?: string }
  | { type: "WORKSPACE_LOAD_SUCCEEDED"; workspace: CoreWorkspaceSnapshot; workspaceName?: string }
  | { type: "WORKSPACE_LOAD_FAILED"; error: WorkspaceError }
  | { type: "BOOTSTRAP_STARTED"; projectId: string; workspaceName: string; prompt?: string; hasMedia: boolean }
  | { type: "EVENT_STREAM_CONNECT_STARTED" }
  | { type: "EVENT_STREAM_CONNECTED" }
  | { type: "EVENT_STREAM_DISCONNECTED" }
  | { type: "EVENT_STREAM_RECONNECTING" }
  | { type: "EVENT_STREAM_MAX_ATTEMPTS_REACHED" }
  | { type: "WORKSPACE_SNAPSHOT_RECEIVED"; workspace: CoreWorkspaceSnapshot; sequence: number }
  | { type: "EDIT_DRAFT_UPDATED"; editDraft: CoreEditDraft; sequence: number }
  | { type: "PROJECT_UPDATED"; project: CoreProject; sequence: number }
  | { type: "CHAT_TURN_CREATED"; turn: CoreChatTurn; sequence: number }
  | { type: "TASK_UPDATED"; task: CoreTask; workflowState: WorkflowState; sequence: number }
  | { type: "ERROR_OCCURRED"; error: WorkspaceError; workflowState?: WorkflowState; sequence: number }
  | { type: "ASSET_UPLOAD_STARTED"; task: ActiveTask }
  | { type: "ASSET_UPLOAD_CANCELLED" }
  | { type: "ASSET_UPLOAD_FAILED"; error: WorkspaceError }
  | { type: "CHAT_REQUEST_ACCEPTED"; task: ActiveTask }
  | { type: "CHAT_FAILED"; error: WorkspaceError }
  | { type: "EXPORT_STARTED"; task: ActiveTask }
  | { type: "EXPORT_COMPLETED"; result: ExportResult; sequence: number }
  | { type: "EXPORT_FAILED"; error: WorkspaceError }
  | {
      type: "SELECTION_CONTEXT_UPDATED";
      scope: RuntimeScope;
      selectedSceneId?: string | null;
      selectedShotId?: string | null;
    }
  | { type: "CLEAR_ERROR" };

interface WorkspaceState {
  workspaceId: string | null;
  workspaceName: string | null;
  runtimeState: SessionRuntimeState;
  editDraft: CoreEditDraft | null;
  assets: WorkspaceAssetItem[];
  clips: WorkspaceClipItem[];
  storyboard: StoryboardScene[];
  currentProject: Record<string, unknown> | null;
  chatTurns: ChatTurn[];
  exportResult: ExportResult | null;
  pendingPrompt: string | null;
  lastEventSequence: number;
  lastError: WorkspaceError | null;

  loadState: WorkspaceLoadState;
  workflowState: WorkflowState | null;
  chatState: ChatState;
  activeTask: ActiveTask | null;
  eventStreamState: EventStreamState;
  reconnectState: ReconnectState;

  // Transitional compatibility fields for existing page components.
  isLoadingWorkspace: boolean;
  isMediaProcessing: boolean;
  mediaStatusText: string | null;
  isThinking: boolean;
  isExporting: boolean;
  processingPhase: ProcessingPhase;
  activeTaskType: string | null;

  connectProjectEvents: (workspaceId: string) => void;
  disconnectProjectEvents: () => void;
  initializeWorkspace: (workspaceId: string, workspaceName?: string) => Promise<void>;
  bootstrapFromLaunch: (input: BootstrapInput) => Promise<void>;
  setSelectionContext: (input: {
    scope: RuntimeScope;
    selectedSceneId?: string | null;
    selectedShotId?: string | null;
  }) => void;
  assembleActionContext: (actionType: Parameters<typeof assembleActionContext>[0]["actionType"]) => ContextAssemblyResult;
  runAgentLoop: (actionType: PlannerActionType) => Promise<RunExecutionLoopResult>;
  uploadAssets: (input?: UploadAssetsInput) => Promise<void>;
  sendChat: (prompt: string) => Promise<void>;
  exportProject: () => Promise<ExportResult | null>;
  clearLastError: () => void;
}

const MAX_RECONNECT_ATTEMPTS = 4;
const RECONNECT_DELAY_MS = 1200;
const plannerRunner = createLlmPlannerRunner(createHeuristicPlannerRunner());
const toolExecutor = createLocalToolExecutor();

let projectEventsSocket: WebSocket | null = null;
let socketProjectId: string | null = null;
let reconnectTimerId: number | null = null;
let reconnectAttempts = 0;
let shouldReconnect = false;
let activeWorkspaceLoadToken = 0;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function toWorkspaceError(message: string, error: unknown): WorkspaceError {
  const maybe = toRequestError(error);
  return {
    code: maybe.code,
    message: maybe.message || message,
    cause:
      typeof maybe.details?.cause === "string"
        ? maybe.details.cause
        : error instanceof Error
        ? error.message
        : undefined,
    requestId: maybe.requestId,
  };
}

function formatDurationLabel(durationMs: number): string {
  return `${Math.max(1, Math.round(durationMs / 1000))}s`;
}

function formatTimeLabel(timeMs: number): string {
  return `${Math.max(0, Math.round(timeMs / 1000))}s`;
}

function clipThumbClass(index: number): string {
  return `thumb-gradient-${(index % 4) + 1}`;
}

function sceneColorClass(index: number): string {
  return ["bg-sky-200", "bg-amber-200", "bg-emerald-200", "bg-rose-200"][index % 4]!;
}

function sceneBgClass(index: number): string {
  return [
    "from-sky-50 to-sky-100",
    "from-amber-50 to-amber-100",
    "from-emerald-50 to-emerald-100",
    "from-rose-50 to-rose-100",
  ][index % 4]!;
}

function mapAssets(editDraft: CoreEditDraft): WorkspaceAssetItem[] {
  return editDraft.assets.map((asset) => ({
    id: asset.id,
    name: asset.name,
    duration: formatDurationLabel(asset.duration_ms),
    type: asset.type,
    sourcePath: asset.source_path ?? null,
  }));
}

function mapClips(editDraft: CoreEditDraft): WorkspaceClipItem[] {
  const assetsById = new Map(editDraft.assets.map((asset) => [asset.id, asset]));
  return editDraft.clips.map((clip, index) => ({
    id: clip.id,
    parent: assetsById.get(clip.asset_id)?.name ?? "Unknown Asset",
    start: formatTimeLabel(clip.source_start_ms),
    end: formatTimeLabel(clip.source_end_ms),
    score:
      typeof clip.confidence === "number"
        ? `${Math.round(Math.max(0, Math.min(1, clip.confidence)) * 100)}`
        : "n/a",
    desc: clip.visual_desc,
    thumbClass: clip.thumbnail_ref ?? clipThumbClass(index),
  }));
}

function mapStoryboard(editDraft: CoreEditDraft): StoryboardScene[] {
  if (!editDraft.scenes || editDraft.scenes.length === 0) {
    return [];
  }

  const shotsById = new Map(editDraft.shots.map((shot) => [shot.id, shot]));
  return editDraft.scenes
    .filter((scene) => scene.enabled)
    .sort((left, right) => left.order - right.order)
    .map((scene, index) => {
      const sceneShots = scene.shot_ids
        .map((shotId) => shotsById.get(shotId))
        .filter((shot): shot is CoreShot => Boolean(shot))
        .sort((left, right) => left.order - right.order);
      const durationMs = sceneShots.reduce(
        (total, shot) => total + Math.max(0, shot.source_out_ms - shot.source_in_ms),
        0
      );
      return {
        id: scene.id,
        title: scene.label?.trim() || `Scene ${index + 1}`,
        duration: formatDurationLabel(durationMs),
        intent: scene.intent?.trim() || sceneShots[0]?.intent?.trim() || "No scene intent yet",
        colorClass: sceneColorClass(index),
        bgClass: sceneBgClass(index),
        shotIds: scene.shot_ids,
        primaryClipId: sceneShots[0]?.clip_id ?? null,
      };
    });
}

function mapTurns(turns: CoreChatTurn[]): ChatTurn[] {
  return turns.map((turn) => {
    if (turn.role === "user") {
      return turn as UserTurn;
    }
    return {
      ...(turn as CoreChatAssistantTurn),
    };
  });
}

function mapTask(task: CoreTask | null): ActiveTask | null {
  if (!task) {
    return null;
  }
  return {
    id: task.id,
    type: task.type,
    status: task.status,
    progress: task.progress,
    message: task.message,
  };
}

function buildCurrentProject(input: {
  project: CoreProject;
  assets: WorkspaceAssetItem[];
  clips: WorkspaceClipItem[];
  storyboard: StoryboardScene[];
  editDraft: CoreEditDraft;
}): Record<string, unknown> {
  return {
    project_id: input.project.id,
    title: input.project.title,
    workflow_state: input.project.workflow_state,
    edit_draft_id: input.editDraft.id,
    edit_draft_version: input.editDraft.version,
    storyboard_count: input.storyboard.length,
    asset_count: input.assets.length,
    clip_count: input.clips.length,
    shot_count: input.editDraft.shots.length,
    mode: "core",
  };
}

function mapWorkspace(workspace: CoreWorkspaceSnapshot, workspaceName?: string): Partial<WorkspaceState> {
  const editDraft = workspace.edit_draft;
  const assets = mapAssets(editDraft);
  const clips = mapClips(editDraft);
  const storyboard = mapStoryboard(editDraft);
  return {
    workspaceId: workspace.project.id,
    workspaceName: workspaceName ?? workspace.project.title,
    editDraft,
    assets,
    clips,
    storyboard,
    chatTurns: mapTurns(workspace.chat_turns),
    currentProject: buildCurrentProject({
      project: workspace.project,
      assets,
      clips,
      storyboard,
      editDraft,
    }),
    workflowState: workspace.project.workflow_state,
    activeTask: mapTask(workspace.active_task),
  };
}

function appendTurn(turns: ChatTurn[], nextTurn: ChatTurn): ChatTurn[] {
  if (turns.some((turn) => turn.id === nextTurn.id)) {
    return turns;
  }
  return [...turns, nextTurn];
}

function deriveProcessingPhase(
  workflowState: WorkflowState | null,
  activeTask: ActiveTask | null
): ProcessingPhase {
  if (activeTask?.type === "index" && activeTask.status === "running") {
    return "indexing";
  }
  if (activeTask?.type === "ingest" && activeTask.status === "running") {
    return "media_processing";
  }
  if (activeTask?.type === "chat" && activeTask.status === "running") {
    return "chat_thinking";
  }
  if (workflowState === "failed") {
    return "failed";
  }
  if (workflowState === null) {
    return "idle";
  }
  return "ready";
}

function withDerivedFields(
  state: Pick<
    WorkspaceState,
    | "runtimeState"
    | "loadState"
    | "workflowState"
    | "chatState"
    | "activeTask"
    | "eventStreamState"
    | "reconnectState"
    | "workspaceId"
    | "workspaceName"
    | "editDraft"
    | "assets"
    | "clips"
    | "storyboard"
    | "currentProject"
    | "chatTurns"
    | "exportResult"
    | "pendingPrompt"
    | "lastEventSequence"
    | "lastError"
  >
): Partial<WorkspaceState> {
  const activeTaskType =
    state.activeTask && state.activeTask.status === "running" ? state.activeTask.type : null;
  const isMediaProcessing = activeTaskType === "ingest";
  const isThinking = state.chatState === "responding";
  const isExporting = activeTaskType === "render";

  return {
    isLoadingWorkspace: state.loadState === "loading",
    isMediaProcessing,
    mediaStatusText:
      isMediaProcessing || isExporting ? state.activeTask?.message ?? null : null,
    isThinking,
    isExporting,
    processingPhase: deriveProcessingPhase(state.workflowState, state.activeTask),
    activeTaskType,
  };
}

function reduceWorkspaceState(
  state: Pick<
    WorkspaceState,
    | "workspaceId"
    | "workspaceName"
    | "runtimeState"
    | "editDraft"
    | "assets"
    | "clips"
    | "storyboard"
    | "currentProject"
    | "chatTurns"
    | "exportResult"
    | "pendingPrompt"
    | "lastEventSequence"
    | "lastError"
    | "loadState"
    | "workflowState"
    | "chatState"
    | "activeTask"
    | "eventStreamState"
    | "reconnectState"
  >,
  event: WorkspaceEvent
): Partial<WorkspaceState> {
  switch (event.type) {
    case "WORKSPACE_LOAD_STARTED":
      return {
        workspaceId: event.workspaceId,
        workspaceName: event.workspaceName ?? state.workspaceName,
        loadState: "loading",
        lastError: null,
      };
    case "WORKSPACE_LOAD_SUCCEEDED":
      return {
        ...mapWorkspace(event.workspace, event.workspaceName),
        runtimeState: syncRuntimeStateFromWorkspace(state.runtimeState, event.workspace),
        loadState: "ready",
        chatState:
          event.workspace.active_task?.type === "chat" &&
          (event.workspace.active_task.status === "queued" || event.workspace.active_task.status === "running")
            ? "responding"
            : "idle",
        lastError: null,
      };
    case "WORKSPACE_LOAD_FAILED":
      return {
        runtimeState: createEmptySessionRuntimeState(),
        editDraft: null,
        assets: [],
        clips: [],
        storyboard: [],
        currentProject: null,
        chatTurns: [],
        loadState: "failed",
        workflowState: "failed",
        chatState: "failed",
        activeTask: null,
        lastError: event.error,
      };
    case "BOOTSTRAP_STARTED":
      return {
        workspaceId: event.projectId,
        workspaceName: event.workspaceName,
        runtimeState: {
          ...createEmptySessionRuntimeState(),
          projectId: event.projectId,
        },
        editDraft: null,
        pendingPrompt: event.prompt?.trim() ?? null,
        exportResult: null,
        lastEventSequence: 0,
        lastError: null,
        loadState: "idle",
        workflowState: event.hasMedia ? "media_ready" : "prompt_input_required",
        chatState: "idle",
        activeTask: null,
        reconnectState: "idle",
      };
    case "EVENT_STREAM_CONNECT_STARTED":
      return {
        eventStreamState: "connecting",
      };
    case "EVENT_STREAM_CONNECTED":
      return {
        eventStreamState: "connected",
        reconnectState: "idle",
      };
    case "EVENT_STREAM_DISCONNECTED":
      return {
        eventStreamState: "disconnected",
      };
    case "EVENT_STREAM_RECONNECTING":
      return {
        reconnectState: "reconnecting",
      };
    case "EVENT_STREAM_MAX_ATTEMPTS_REACHED":
      return {
        reconnectState: "max_attempts_reached",
        eventStreamState: "disconnected",
      };
    case "WORKSPACE_SNAPSHOT_RECEIVED":
      return {
        ...mapWorkspace(event.workspace),
        runtimeState: syncRuntimeStateFromWorkspace(state.runtimeState, event.workspace),
        loadState: "ready",
        chatState:
          event.workspace.active_task?.type === "chat" &&
          (event.workspace.active_task.status === "queued" || event.workspace.active_task.status === "running")
            ? "responding"
            : "idle",
        lastEventSequence: Math.max(state.lastEventSequence, event.sequence),
      };
    case "EDIT_DRAFT_UPDATED": {
      const assets = mapAssets(event.editDraft);
      const clips = mapClips(event.editDraft);
      const storyboard = mapStoryboard(event.editDraft);
      const currentProject = buildCurrentProject({
        project: {
          id: String(state.workspaceId ?? ""),
          title: String(state.workspaceName ?? ""),
          workflow_state: (state.workflowState ?? "media_ready") as ProjectWorkflowState,
          created_at: "",
          updated_at: "",
        },
        assets,
        clips,
        storyboard,
        editDraft: event.editDraft,
      });
      return {
        editDraft: event.editDraft,
        runtimeState: syncRuntimeStateFromWorkspace(state.runtimeState, {
          project: {
            id: String(state.workspaceId ?? ""),
            title: String(state.workspaceName ?? ""),
            workflow_state: (state.workflowState ?? "media_ready") as ProjectWorkflowState,
            created_at: "",
            updated_at: "",
          },
          edit_draft: event.editDraft,
          chat_turns: [],
          active_task: null,
        }),
        assets,
        clips,
        storyboard,
        currentProject,
        lastEventSequence: Math.max(state.lastEventSequence, event.sequence),
      };
    }
    case "SELECTION_CONTEXT_UPDATED":
      return {
        runtimeState: updateSelectionState(state.runtimeState, {
          scope: event.scope,
          selectedSceneId: event.selectedSceneId,
          selectedShotId: event.selectedShotId,
        }),
      };
    case "PROJECT_UPDATED": {
      const currentProject = buildCurrentProject({
        project: event.project,
        assets: state.assets,
        clips: state.clips,
        storyboard: state.storyboard,
        editDraft:
          state.editDraft ??
          ({
            id: "",
            project_id: event.project.id,
            version: 0,
            status: "draft",
            assets: [],
            clips: [],
            shots: [],
            scenes: null,
            selected_scene_id: null,
            selected_shot_id: null,
            created_at: "",
            updated_at: "",
          } as CoreEditDraft),
      });
      return {
        currentProject,
        workflowState: event.project.workflow_state,
        lastEventSequence: Math.max(state.lastEventSequence, event.sequence),
      };
    }
    case "CHAT_TURN_CREATED":
      return {
        chatTurns: appendTurn(
          state.chatTurns,
          event.turn.role === "user"
            ? (event.turn as UserTurn)
            : ({
                ...(event.turn as CoreChatAssistantTurn),
              } as AssistantDecisionTurn)
        ),
        lastEventSequence: Math.max(state.lastEventSequence, event.sequence),
      };
    case "TASK_UPDATED": {
      const activeTask =
        event.task.status === "queued" || event.task.status === "running" ? mapTask(event.task) : null;
      const nextChatState =
        event.task.type === "chat" && (event.task.status === "queued" || event.task.status === "running")
          ? "responding"
          : event.task.type === "chat" && event.task.status === "failed"
          ? "failed"
          : "idle";
      return {
        activeTask,
        workflowState: event.workflowState,
        chatState: nextChatState,
        lastEventSequence: Math.max(state.lastEventSequence, event.sequence),
        lastError: event.task.status === "failed" ? state.lastError : null,
      };
    }
    case "ERROR_OCCURRED":
      return {
        workflowState: event.workflowState ?? state.workflowState,
        lastError: event.error,
        lastEventSequence: Math.max(state.lastEventSequence, event.sequence),
      };
    case "ASSET_UPLOAD_STARTED":
      return {
        activeTask: event.task,
        workflowState: "media_processing",
        lastError: null,
      };
    case "ASSET_UPLOAD_CANCELLED":
      return {
        activeTask: null,
      };
    case "ASSET_UPLOAD_FAILED":
      return {
        workflowState: "failed",
        activeTask: null,
        lastError: event.error,
      };
    case "CHAT_REQUEST_ACCEPTED":
      return {
        chatState: "responding",
        workflowState: "chat_thinking",
        activeTask: event.task,
        lastError: null,
      };
    case "CHAT_FAILED":
      return {
        chatState: "failed",
        workflowState: "failed",
        activeTask: null,
        lastError: event.error,
      };
    case "EXPORT_STARTED":
      return {
        exportResult: null,
        workflowState: "rendering",
        activeTask: event.task,
        lastError: null,
      };
    case "EXPORT_COMPLETED":
      return {
        exportResult: event.result,
        workflowState: "ready",
        lastEventSequence: Math.max(state.lastEventSequence, event.sequence),
      };
    case "EXPORT_FAILED":
      return {
        workflowState: "failed",
        activeTask: null,
        lastError: event.error,
      };
    case "CLEAR_ERROR":
      return {
        lastError: null,
      };
    default:
      return state;
  }
}

function clearReconnectTimer(): void {
  if (reconnectTimerId !== null) {
    window.clearTimeout(reconnectTimerId);
    reconnectTimerId = null;
  }
}

function closeProjectSocket(): void {
  if (projectEventsSocket) {
    projectEventsSocket.onopen = null;
    projectEventsSocket.onmessage = null;
    projectEventsSocket.onerror = null;
    projectEventsSocket.onclose = null;
    projectEventsSocket.close();
    projectEventsSocket = null;
  }
  socketProjectId = null;
}

const initialState: Omit<
  WorkspaceState,
  | "connectProjectEvents"
  | "disconnectProjectEvents"
  | "initializeWorkspace"
  | "bootstrapFromLaunch"
  | "setSelectionContext"
  | "assembleActionContext"
  | "runAgentLoop"
  | "uploadAssets"
  | "sendChat"
  | "exportProject"
  | "clearLastError"
> = {
  workspaceId: null,
  workspaceName: null,
  runtimeState: createEmptySessionRuntimeState(),
  editDraft: null,
  assets: [],
  clips: [],
  storyboard: [],
  currentProject: null,
  chatTurns: [],
  exportResult: null,
  pendingPrompt: null,
  lastEventSequence: 0,
  lastError: null,
  loadState: "idle",
  workflowState: null,
  chatState: "idle",
  activeTask: null,
  eventStreamState: "disconnected",
  reconnectState: "idle",
  isLoadingWorkspace: false,
  isMediaProcessing: false,
  mediaStatusText: null,
  isThinking: false,
  isExporting: false,
  processingPhase: "idle",
  activeTaskType: null,
};

export const useWorkspaceStore = create<WorkspaceState>((set, get) => {
  const dispatch = (event: WorkspaceEvent) => {
    set((state) => {
      const patch = reduceWorkspaceState(state, event);
      const nextState = {
        ...state,
        ...patch,
      };
      return {
        ...patch,
        ...withDerivedFields(nextState),
      };
    });
  };

  const applyDirectPatch = (patch: Partial<WorkspaceState>) => {
    set((state) => {
      const nextState = {
        ...state,
        ...patch,
      };
      return {
        ...patch,
        ...withDerivedFields(nextState),
      };
    });
  };

  const handleEventEnvelope = (payload: CoreEventEnvelope) => {
    switch (payload.event) {
      case "workspace.snapshot":
        dispatch({
          type: "WORKSPACE_SNAPSHOT_RECEIVED",
          workspace: (payload.data as { workspace: CoreWorkspaceSnapshot }).workspace,
          sequence: payload.sequence,
        });
        break;
      case "task.updated": {
        const data = payload.data as { task: CoreTask; workflow_state: WorkflowState };
        dispatch({
          type: "TASK_UPDATED",
          task: data.task,
          workflowState: data.workflow_state,
          sequence: payload.sequence,
        });
        if (
          data.task.type === "ingest" &&
          data.task.status === "succeeded" &&
          get().pendingPrompt?.trim() &&
          get().assets.length > 0
        ) {
          const queuedPrompt = get().pendingPrompt!.trim();
          applyDirectPatch({ pendingPrompt: null });
          void get().sendChat(queuedPrompt);
        }
        break;
      }
      case "chat.turn.created":
        dispatch({
          type: "CHAT_TURN_CREATED",
          turn: (payload.data as { turn: CoreChatTurn }).turn,
          sequence: payload.sequence,
        });
        break;
      case "edit_draft.updated":
        dispatch({
          type: "EDIT_DRAFT_UPDATED",
          editDraft: (payload.data as { edit_draft: CoreEditDraft }).edit_draft,
          sequence: payload.sequence,
        });
        break;
      case "project.updated":
        dispatch({
          type: "PROJECT_UPDATED",
          project: (payload.data as { project: CoreProject }).project,
          sequence: payload.sequence,
        });
        break;
      case "export.completed":
        dispatch({
          type: "EXPORT_COMPLETED",
          result: (payload.data as { result: ExportResult }).result,
          sequence: payload.sequence,
        });
        break;
      case "error.occurred": {
        const data = payload.data as {
          code: string;
          message: string;
          workflow_state?: WorkflowState;
        };
        dispatch({
          type: "ERROR_OCCURRED",
          error: {
            code: data.code,
            message: data.message,
          },
          workflowState: data.workflow_state,
          sequence: payload.sequence,
        });
        break;
      }
      default:
        break;
    }
  };

  const openProjectEvents = (workspaceId: string) => {
    if (
      socketProjectId === workspaceId &&
      projectEventsSocket &&
      (projectEventsSocket.readyState === WebSocket.CONNECTING ||
        projectEventsSocket.readyState === WebSocket.OPEN)
    ) {
      return;
    }
    clearReconnectTimer();
    closeProjectSocket();
    shouldReconnect = true;
    socketProjectId = workspaceId;
    dispatch({ type: "EVENT_STREAM_CONNECT_STARTED" });

    const socket = createProjectEventsSocket(workspaceId);
    projectEventsSocket = socket;

    socket.onopen = () => {
      reconnectAttempts = 0;
      dispatch({ type: "EVENT_STREAM_CONNECTED" });
    };

    socket.onmessage = (event) => {
      try {
        handleEventEnvelope(JSON.parse(event.data) as CoreEventEnvelope);
      } catch (error) {
        dispatch({
          type: "ERROR_OCCURRED",
          error: toWorkspaceError("event_stream_parse_failed", error),
          sequence: get().lastEventSequence,
        });
      }
    };

    socket.onerror = () => {
      dispatch({
        type: "EVENT_STREAM_RECONNECTING",
      });
    };

    socket.onclose = () => {
      projectEventsSocket = null;
      if (!shouldReconnect || get().workspaceId !== workspaceId) {
        dispatch({ type: "EVENT_STREAM_DISCONNECTED" });
        return;
      }
      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        dispatch({ type: "EVENT_STREAM_MAX_ATTEMPTS_REACHED" });
        return;
      }
      reconnectAttempts += 1;
      dispatch({ type: "EVENT_STREAM_RECONNECTING" });
      reconnectTimerId = window.setTimeout(() => {
        openProjectEvents(workspaceId);
      }, RECONNECT_DELAY_MS);
    };
  };

  return {
    ...initialState,

    connectProjectEvents: (workspaceId) => {
      openProjectEvents(workspaceId);
    },

    disconnectProjectEvents: () => {
      shouldReconnect = false;
      reconnectAttempts = 0;
      clearReconnectTimer();
      closeProjectSocket();
      dispatch({ type: "EVENT_STREAM_DISCONNECTED" });
    },

    initializeWorkspace: async (workspaceId, workspaceName) => {
      const loadToken = ++activeWorkspaceLoadToken;
      const shouldResetConnection = get().workspaceId !== workspaceId;
      if (shouldResetConnection) {
        get().disconnectProjectEvents();
      }
      dispatch({ type: "WORKSPACE_LOAD_STARTED", workspaceId, workspaceName });

      try {
        const response = await getWorkspace(workspaceId);
        if (loadToken !== activeWorkspaceLoadToken) {
          return;
        }
        dispatch({ type: "WORKSPACE_LOAD_SUCCEEDED", workspace: response.workspace, workspaceName });
        get().connectProjectEvents(workspaceId);
      } catch (error) {
        if (loadToken !== activeWorkspaceLoadToken) {
          return;
        }
        dispatch({
          type: "WORKSPACE_LOAD_FAILED",
          error: toWorkspaceError("load_workspace_failed", error),
        });
      }
    },

    bootstrapFromLaunch: async (input) => {
      const trimmedPrompt = input.prompt?.trim();
      dispatch({
        type: "BOOTSTRAP_STARTED",
        projectId: input.projectId,
        workspaceName: input.workspaceName,
        prompt: trimmedPrompt,
        hasMedia: input.hasMedia,
      });

      await get().initializeWorkspace(input.projectId, input.workspaceName);
      if (get().loadState !== "ready") {
        return;
      }

      if (trimmedPrompt && input.hasMedia) {
        for (let attempt = 0; attempt < 8; attempt += 1) {
          if (get().eventStreamState === "connected") {
            break;
          }
          await sleep(50);
        }
        await get().sendChat(trimmedPrompt);
      }
    },

    setSelectionContext: (input) => {
      dispatch({
        type: "SELECTION_CONTEXT_UPDATED",
        scope: input.scope,
        selectedSceneId: input.selectedSceneId,
        selectedShotId: input.selectedShotId,
      });
    },

    assembleActionContext: (actionType) => {
      return assembleActionContext({
        actionType,
        runtimeState: get().runtimeState,
      });
    },

    runAgentLoop: async (actionType) => {
      const result = await runExecutionLoop(
        {
          plannerRunner,
          toolExecutor,
        },
        {
          runtimeState: get().runtimeState,
          actionType,
        },
      );
      applyDirectPatch({
        runtimeState: result.finalRuntimeState,
      });
      return result;
    },

    uploadAssets: async (input) => {
      const workspaceId = get().workspaceId;
      if (!workspaceId) {
        applyDirectPatch({
          lastError: {
            code: "WORKSPACE_NOT_READY",
            message: "workspace_not_ready",
          },
        });
        return;
      }

      let media = normalizeMediaInput(input);
      if (!media && input?.shouldPickMedia) {
        media = await pickMediaFromSystem();
      }
      if (!media) {
        dispatch({ type: "ASSET_UPLOAD_CANCELLED" });
        return;
      }

      const mediaReference = toMediaReference(media);
      if (!mediaReference) {
        dispatch({
          type: "ASSET_UPLOAD_FAILED",
          error: {
            code: "INVALID_MEDIA_REFERENCE",
            message: "invalid_media_reference",
          },
        });
        return;
      }

      try {
        registerProjectMediaSources(workspaceId, media);
        const response = await importAssetsRequest(workspaceId, { media: mediaReference });
        dispatch({
          type: "ASSET_UPLOAD_STARTED",
          task: mapTask(response.task)!,
        });
      } catch (error) {
        dispatch({
          type: "ASSET_UPLOAD_FAILED",
          error: toWorkspaceError("upload_assets_failed", error),
        });
      }
    },

    sendChat: async (prompt) => {
      const workspaceId = get().workspaceId;
      const trimmedPrompt = prompt.trim();
      if (!workspaceId || !trimmedPrompt) {
        return;
      }

      if (get().chatState === "responding") {
        return;
      }

      if (get().assets.length === 0) {
        applyDirectPatch({ pendingPrompt: trimmedPrompt });
        return;
      }

      try {
        const selection = get().runtimeState.selection;
        const response = await sendChatRequest(workspaceId, {
          prompt: trimmedPrompt,
          target:
            selection.scope === "global"
              ? undefined
              : {
                  scene_id: selection.selectedSceneId,
                  shot_id: selection.scope === "shot" ? selection.selectedShotId : undefined,
                },
        });
        applyDirectPatch({
          runtimeState: recordExecutionAction(get().runtimeState, {
            action: "apply_patch",
            status: "running",
            summary:
              selection.scope === "global"
                ? "chat_request_scope_global"
                : `chat_request_scope_${selection.scope}`,
            targetSceneId: selection.selectedSceneId,
            targetShotId: selection.selectedShotId,
          }),
        });
        dispatch({
          type: "CHAT_REQUEST_ACCEPTED",
          task: mapTask(response.task)!,
        });
      } catch (error) {
        dispatch({
          type: "CHAT_FAILED",
          error: toWorkspaceError("send_chat_failed", error),
        });
      }
    },

    exportProject: async () => {
      const workspaceId = get().workspaceId;
      if (!workspaceId) {
        applyDirectPatch({
          lastError: {
            code: "WORKSPACE_NOT_READY",
            message: "workspace_not_ready",
          },
        });
        return null;
      }

      try {
        const response = await exportProjectRequest(workspaceId, {});
        dispatch({
          type: "EXPORT_STARTED",
          task: mapTask(response.task)!,
        });
        return null;
      } catch (error) {
        dispatch({
          type: "EXPORT_FAILED",
          error: toWorkspaceError("export_failed", error),
        });
        return null;
      }
    },

    clearLastError: () => {
      dispatch({ type: "CLEAR_ERROR" });
    },
  };
});
