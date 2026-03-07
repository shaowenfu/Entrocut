import { create } from "zustand";
import { normalizeMediaInput, pickMediaFromSystem, type MediaPickInput } from "../services/electronBridge";
import {
  addPrototypeAssets,
  applyPrototypePrompt,
  exportPrototypeProject,
  getPrototypeProject,
  type PrototypeAgentOperation,
  type PrototypeAssistantTurn,
  type PrototypeAsset,
  type PrototypeChatTurn,
  type PrototypeClip,
  type PrototypeDecisionType,
  type PrototypeProjectRecord,
  type PrototypeScene,
  type PrototypeUserTurn,
} from "../mocks/prototypeWorkspace";

export interface WorkspaceAssetItem {
  id: string;
  name: string;
  duration: string;
  type: "video" | "audio";
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
}

export interface UserTurn {
  id: string;
  role: "user";
  content: string;
}

export interface AssistantDecisionTurn {
  id: string;
  role: "assistant";
  type: "decision";
  decision_type: PrototypeDecisionType;
  reasoning_summary: string;
  ops: PrototypeAgentOperation[];
}

export type ChatTurn = UserTurn | AssistantDecisionTurn;

type ProcessingPhase = "idle" | "media_processing" | "indexing" | "chat_thinking" | "ready" | "failed";
type WorkflowState =
  | "prompt_input_required"
  | "awaiting_media"
  | "media_ready"
  | "media_processing"
  | "chat_thinking"
  | "ready"
  | "rendering"
  | "failed";
type WorkspaceLoadState = "idle" | "loading" | "ready" | "failed";
type ChatState = "idle" | "responding" | "failed";
type EventStreamState = "disconnected" | "connecting" | "connected";
type ReconnectState = "idle" | "reconnecting" | "max_attempts_reached";
type TaskType = "ingest" | "index" | "chat" | "render";
type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

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

interface ExportResult {
  render_type: "export";
  output_url: string;
  duration_ms: number;
  file_size_bytes: number | null;
  thumbnail_url: string | null;
  format: string;
  quality: string | null;
  resolution: string | null;
}

interface ActiveTask {
  id: string;
  type: TaskType;
  status: TaskStatus;
  progress?: number;
  message?: string | null;
}

type WorkspaceEvent =
  | { type: "WORKSPACE_LOAD_STARTED"; workspaceId: string; workspaceName?: string }
  | { type: "WORKSPACE_LOAD_SUCCEEDED"; record: PrototypeProjectRecord; workspaceName?: string }
  | { type: "WORKSPACE_LOAD_FAILED"; error: WorkspaceError }
  | { type: "BOOTSTRAP_STARTED"; projectId: string; workspaceName: string; prompt?: string; hasMedia: boolean }
  | { type: "EVENT_STREAM_CONNECT_STARTED" }
  | { type: "EVENT_STREAM_CONNECTED" }
  | { type: "EVENT_STREAM_DISCONNECTED" }
  | { type: "EVENT_STREAM_RECONNECTING" }
  | { type: "EVENT_STREAM_MAX_ATTEMPTS_REACHED" }
  | { type: "ASSET_UPLOAD_STARTED"; task: ActiveTask }
  | { type: "ASSET_UPLOAD_CANCELLED" }
  | { type: "ASSET_UPLOAD_SUCCEEDED"; record: PrototypeProjectRecord }
  | { type: "ASSET_UPLOAD_FAILED"; error: WorkspaceError }
  | { type: "CHAT_STARTED"; prompt: string; task: ActiveTask; userTurn: UserTurn }
  | { type: "CHAT_QUEUED"; prompt: string; userTurn: UserTurn; assistantTurn: AssistantDecisionTurn }
  | { type: "CHAT_SUCCEEDED"; record: PrototypeProjectRecord; hasMedia: boolean }
  | { type: "CHAT_FAILED"; error: WorkspaceError }
  | { type: "EXPORT_STARTED"; task: ActiveTask }
  | { type: "EXPORT_SUCCEEDED"; result: ExportResult }
  | { type: "EXPORT_FAILED"; error: WorkspaceError }
  | { type: "CLEAR_ERROR" };

interface WorkspaceState {
  workspaceId: string | null;
  workspaceName: string | null;
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
  uploadAssets: (input?: UploadAssetsInput) => Promise<void>;
  sendChat: (prompt: string) => Promise<void>;
  exportProject: () => Promise<ExportResult | null>;
  clearLastError: () => void;
}

function toWorkspaceError(message: string, error: unknown): WorkspaceError {
  const maybe = error as {
    code?: string;
    message?: string;
    cause?: string;
    requestId?: string;
    request_id?: string;
  };
  return {
    code: maybe.code ?? "WORKSPACE_ERROR",
    message: maybe.message ?? message,
    cause: maybe.cause,
    requestId:
      typeof maybe.requestId === "string"
        ? maybe.requestId
        : typeof maybe.request_id === "string"
        ? maybe.request_id
        : undefined,
  };
}

function mapAssets(assets: PrototypeAsset[]): WorkspaceAssetItem[] {
  return assets.map((asset) => ({
    id: asset.id,
    name: asset.name,
    duration: asset.duration,
    type: asset.type,
  }));
}

function mapClips(clips: PrototypeClip[]): WorkspaceClipItem[] {
  return clips.map((clip) => ({
    id: clip.id,
    parent: clip.parent,
    start: clip.start,
    end: clip.end,
    score: clip.score,
    desc: clip.desc,
    thumbClass: clip.thumbClass,
  }));
}

function mapStoryboard(storyboard: PrototypeScene[]): StoryboardScene[] {
  return storyboard.map((scene) => ({
    id: scene.id,
    title: scene.title,
    duration: scene.duration,
    intent: scene.intent,
    colorClass: scene.colorClass,
    bgClass: scene.bgClass,
  }));
}

function mapTurns(turns: PrototypeChatTurn[]): ChatTurn[] {
  return turns.map((turn) => {
    if (turn.role === "user") {
      return turn as PrototypeUserTurn;
    }
    return turn as PrototypeAssistantTurn;
  });
}

function buildCurrentProject(record: PrototypeProjectRecord): Record<string, unknown> {
  return {
    project_id: record.id,
    title: record.title,
    storyboard_count: record.storyboard.length,
    asset_count: record.assets.length,
    clip_count: record.clips.length,
    mode: "prototype",
  };
}

function mapRecord(record: PrototypeProjectRecord, workspaceName?: string): Partial<WorkspaceState> {
  return {
    workspaceId: record.id,
    workspaceName: workspaceName ?? record.title,
    assets: mapAssets(record.assets),
    clips: mapClips(record.clips),
    storyboard: mapStoryboard(record.storyboard),
    chatTurns: mapTurns(record.chatTurns),
    currentProject: buildCurrentProject(record),
    lastEventSequence: Date.now(),
  };
}

function createId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 10)}`;
  }
  return `${prefix}_${Math.random().toString(16).slice(2, 12)}`;
}

function createTask(type: TaskType, message?: string): ActiveTask {
  return {
    id: createId(`task_${type}`),
    type,
    status: "running",
    message: message ?? null,
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
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
    | "loadState"
    | "workflowState"
    | "chatState"
    | "activeTask"
    | "eventStreamState"
    | "reconnectState"
    | "workspaceId"
    | "workspaceName"
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
        ...mapRecord(event.record, event.workspaceName),
        loadState: "ready",
        workflowState: event.record.assets.length > 0 ? "ready" : "awaiting_media",
        chatState: "idle",
        activeTask: null,
        eventStreamState: "connected",
        reconnectState: "idle",
      };
    case "WORKSPACE_LOAD_FAILED":
      return {
        assets: [],
        clips: [],
        storyboard: [],
        currentProject: null,
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
        assets: [],
        clips: [],
        storyboard: [],
        currentProject: null,
        chatTurns: [],
        exportResult: null,
        pendingPrompt: event.prompt?.trim() ?? null,
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
        reconnectState: "idle",
      };
    case "EVENT_STREAM_RECONNECTING":
      return {
        reconnectState: "reconnecting",
      };
    case "EVENT_STREAM_MAX_ATTEMPTS_REACHED":
      return {
        reconnectState: "max_attempts_reached",
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
    case "ASSET_UPLOAD_SUCCEEDED":
      return {
        ...mapRecord(event.record),
        workflowState: "ready",
        activeTask: null,
        chatState: "idle",
      };
    case "ASSET_UPLOAD_FAILED":
      return {
        workflowState: "failed",
        activeTask: null,
        lastError: event.error,
      };
    case "CHAT_STARTED":
      return {
        chatTurns: [...state.chatTurns, event.userTurn],
        chatState: "responding",
        workflowState: "chat_thinking",
        activeTask: event.task,
        lastError: null,
      };
    case "CHAT_QUEUED":
      return {
        pendingPrompt: event.prompt,
        chatTurns: [...state.chatTurns, event.userTurn, event.assistantTurn],
      };
    case "CHAT_SUCCEEDED":
      return {
        ...mapRecord(event.record),
        chatState: "idle",
        workflowState: event.hasMedia ? "ready" : "awaiting_media",
        activeTask: null,
        pendingPrompt: null,
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
    case "EXPORT_SUCCEEDED":
      return {
        exportResult: event.result,
        workflowState: "ready",
        activeTask: null,
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

const initialState: Omit<
  WorkspaceState,
  | "connectProjectEvents"
  | "disconnectProjectEvents"
  | "initializeWorkspace"
  | "bootstrapFromLaunch"
  | "uploadAssets"
  | "sendChat"
  | "exportProject"
  | "clearLastError"
> = {
  workspaceId: null,
  workspaceName: null,
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

  return {
    ...initialState,

    connectProjectEvents: (workspaceId) => {
      void workspaceId;
      dispatch({ type: "EVENT_STREAM_CONNECT_STARTED" });
      dispatch({ type: "EVENT_STREAM_CONNECTED" });
    },

    disconnectProjectEvents: () => {
      dispatch({ type: "EVENT_STREAM_DISCONNECTED" });
    },

    initializeWorkspace: async (workspaceId, workspaceName) => {
      dispatch({ type: "EVENT_STREAM_CONNECT_STARTED" });
      dispatch({ type: "WORKSPACE_LOAD_STARTED", workspaceId, workspaceName });

      try {
        const record = getPrototypeProject(workspaceId);
        if (!record) {
          throw new Error("prototype_project_not_found");
        }
        dispatch({ type: "EVENT_STREAM_CONNECTED" });
        dispatch({ type: "WORKSPACE_LOAD_SUCCEEDED", record, workspaceName });
      } catch (error) {
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

      if (trimmedPrompt) {
        await get().sendChat(trimmedPrompt);
        return;
      }

      if (get().loadState === "ready") {
        applyDirectPatch({
          workflowState: get().assets.length > 0 ? "ready" : "awaiting_media",
        });
      }
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

      dispatch({
        type: "ASSET_UPLOAD_STARTED",
        task: createTask("ingest", "正在刷新 prototype 素材示意..."),
      });

      try {
        await sleep(220);
        const updated = addPrototypeAssets(workspaceId, media);
        if (!updated) {
          throw new Error("prototype_project_not_found");
        }
        dispatch({ type: "ASSET_UPLOAD_SUCCEEDED", record: updated });

        const queuedPrompt = get().pendingPrompt?.trim();
        if (queuedPrompt) {
          applyDirectPatch({ pendingPrompt: null });
          await get().sendChat(queuedPrompt);
        }
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

      if (get().isThinking) {
        return;
      }

      if (get().isMediaProcessing) {
        dispatch({
          type: "CHAT_QUEUED",
          prompt: trimmedPrompt,
          userTurn: {
            id: `user_${Date.now()}`,
            role: "user",
            content: trimmedPrompt,
          },
          assistantTurn: {
            id: `assistant_${Date.now()}`,
            role: "assistant",
            type: "decision",
            decision_type: "ASK_USER_CLARIFICATION",
            reasoning_summary: "素材示意还在刷新，完成后会自动应用这条指令。",
            ops: [{ op: "prompt_queued", note: "Queued in prototype mode" }],
          },
        });
        return;
      }

      dispatch({
        type: "CHAT_STARTED",
        prompt: trimmedPrompt,
        task: createTask("chat", "Analyzing footage and generating edit..."),
        userTurn: {
          id: `user_${Date.now()}`,
          role: "user",
          content: trimmedPrompt,
        },
      });

      try {
        await sleep(320);
        const updated = applyPrototypePrompt(workspaceId, trimmedPrompt);
        if (!updated) {
          throw new Error("prototype_project_not_found");
        }
        dispatch({
          type: "CHAT_SUCCEEDED",
          record: updated,
          hasMedia: updated.assets.length > 0,
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

      if (get().isExporting || get().isMediaProcessing) {
        return null;
      }

      dispatch({
        type: "EXPORT_STARTED",
        task: createTask("render", "正在生成 prototype 导出路径..."),
      });

      try {
        await sleep(280);
        const result = exportPrototypeProject(workspaceId);
        if (!result) {
          throw new Error("prototype_project_not_found");
        }
        dispatch({ type: "EXPORT_SUCCEEDED", result });
        return result;
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
