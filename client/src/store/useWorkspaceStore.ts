import { create } from "zustand";
import {
  closeManagedSocket,
  createManagedProjectEventSocket,
  type CoreEventEnvelope,
  type ReconnectState,
  type SocketManager,
} from "../services/coreEvents";
import {
  coreChat,
  coreGetProject,
  coreImportAssets,
  coreIngestProject,
  coreRender,
  coreUpsertClips,
  coreUploadAssets,
  type CoreAssetDTO,
  type CoreClipDTO,
  type CoreRenderResponse,
} from "../services/coreApi";
import {
  normalizeMediaInput,
  pickMediaFromSystem,
  type MediaPickInput,
} from "../services/electronBridge";
import { getOrCreateSessionId } from "../utils/session";
import type { AgentOperation, DecisionType, EntroVideoProject } from "../contracts/contract";

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
  decision_type: DecisionType;
  reasoning_summary: string;
  ops: AgentOperation[];
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

interface WorkspaceState {
  workspaceId: string | null;
  workspaceName: string | null;
  assets: WorkspaceAssetItem[];
  clips: WorkspaceClipItem[];
  storyboard: StoryboardScene[];
  currentProject: EntroVideoProject | null;
  chatTurns: ChatTurn[];
  isLoadingWorkspace: boolean;
  isMediaProcessing: boolean;
  mediaStatusText: string | null;
  isThinking: boolean;
  isExporting: boolean;
  exportResult: CoreRenderResponse | null;
  processingPhase: ProcessingPhase;
  eventStreamState: "disconnected" | "connecting" | "connected";
  reconnectState: ReconnectState;
  workflowState: WorkflowState | null;
  activeTaskType: string | null;
  lastEventSequence: number;
  pendingPrompt: string | null;
  lastError: WorkspaceError | null;
  connectProjectEvents: (workspaceId: string) => void;
  disconnectProjectEvents: () => void;
  initializeWorkspace: (workspaceId: string, workspaceName?: string) => Promise<void>;
  bootstrapFromLaunch: (input: BootstrapInput) => Promise<void>;
  uploadAssets: (input?: UploadAssetsInput) => Promise<void>;
  sendChat: (prompt: string) => Promise<void>;
  exportProject: () => Promise<CoreRenderResponse | null>;
  clearLastError: () => void;
}

const CLIP_THUMBS = ["thumb-blue", "thumb-indigo", "thumb-purple", "thumb-teal"] as const;
const SCENE_STYLES = [
  { colorClass: "scene-blue", bgClass: "scene-bg-blue" },
  { colorClass: "scene-indigo", bgClass: "scene-bg-indigo" },
  { colorClass: "scene-purple", bgClass: "scene-bg-purple" },
  { colorClass: "scene-cyan", bgClass: "scene-bg-cyan" },
] as const;

let activeProjectSocket: SocketManager | null = null;
let activeProjectSocketId: string | null = null;

function mapMediaStageToPhase(stage: string): ProcessingPhase {
  if (stage === "index") {
    return "indexing";
  }
  return "media_processing";
}

function formatMediaEventMessage(stage: string, payload: Record<string, unknown>): string {
  const message = typeof payload.message === "string" ? payload.message : "";
  if (message && !message.includes("_")) {
    return message;
  }
  switch (stage) {
    case "scan":
      return "视频处理中：正在扫描素材...";
    case "segment":
      return "视频处理中：正在切分镜头...";
    case "extract_frames":
      return "视频处理中：正在提取关键帧...";
    case "embed":
      return "视频处理中：正在生成向量...";
    case "index":
      return "视频处理中：正在向量化片段...";
    case "render":
      return "视频处理中：正在生成预览...";
    default:
      return message || "视频处理中...";
  }
}

function toProcessingPhaseFromWorkflow(
  workflowState: string | null,
  activeTaskType: string | null
): ProcessingPhase {
  if (activeTaskType === "index") {
    return "indexing";
  }
  if (activeTaskType === "ingest" || workflowState === "media_processing") {
    return "media_processing";
  }
  if (activeTaskType === "chat" || workflowState === "chat_thinking") {
    return "chat_thinking";
  }
  if (workflowState === "failed") {
    return "failed";
  }
  if (workflowState === "rendering") {
    return "media_processing";
  }
  return "ready";
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

function pad(value: number): string {
  return value.toString().padStart(2, "0");
}

function toClock(ms: number): string {
  const safe = Math.max(0, Math.floor(ms / 1000));
  const mins = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${pad(mins)}:${pad(secs)}`;
}

function toSceneDuration(ms: number): string {
  const seconds = Math.max(1, Math.round(ms / 1000));
  return `${seconds}s`;
}

function mapAssets(assets: CoreAssetDTO[]): WorkspaceAssetItem[] {
  return assets.map((asset) => ({
    id: asset.asset_id,
    name: asset.name,
    duration: toClock(asset.duration_ms),
    type: asset.type,
  }));
}

function mapClips(clips: CoreClipDTO[]): WorkspaceClipItem[] {
  return clips.map((clip, index) => ({
    id: clip.clip_id,
    parent: clip.asset_id,
    start: toClock(clip.start_ms),
    end: toClock(clip.end_ms),
    score: `${Math.round(Math.max(0, Math.min(1, clip.score)) * 100)}%`,
    desc: clip.description,
    thumbClass: CLIP_THUMBS[index % CLIP_THUMBS.length],
  }));
}

function buildStoryboardFromClips(clips: CoreClipDTO[]): StoryboardScene[] {
  if (clips.length === 0) {
    return [
      {
        id: "scene_pending_1",
        title: "Waiting For Media",
        duration: "5s",
        intent: "Upload media or send prompt to start AI editing.",
        colorClass: "scene-indigo",
        bgClass: "scene-bg-indigo",
      },
    ];
  }

  return clips.slice(0, 4).map((clip, index) => {
    const style = SCENE_STYLES[index % SCENE_STYLES.length];
    return {
      id: `scene_${clip.clip_id}`,
      title: `Scene ${index + 1}`,
      duration: toSceneDuration(clip.end_ms - clip.start_ms),
      intent: clip.description,
      colorClass: style.colorClass,
      bgClass: style.bgClass,
    };
  });
}

function mapStoryboardFromServer(
  scenes: Array<{ id: string; title: string; duration: string; intent: string }> | undefined,
  fallback: StoryboardScene[]
): StoryboardScene[] {
  if (!scenes || scenes.length === 0) {
    return fallback;
  }
  return scenes.map((scene, index) => {
    const style = SCENE_STYLES[index % SCENE_STYLES.length];
    return {
      id: scene.id,
      title: scene.title,
      duration: scene.duration,
      intent: scene.intent,
      colorClass: style.colorClass,
      bgClass: style.bgClass,
    };
  });
}

function applyCoreEvent(event: CoreEventEnvelope): void {
  const setState = useWorkspaceStore.setState;
  const getState = useWorkspaceStore.getState;
  const nextSequence = typeof event.sequence === "number" ? event.sequence : null;
  if (event.event !== "session.ready" && nextSequence !== null && nextSequence <= getState().lastEventSequence) {
    return;
  }
  switch (event.event) {
    case "session.ready":
      setState((state) => {
        const payloadLastSequence =
          typeof event.payload.last_sequence === "number" ? event.payload.last_sequence : nextSequence ?? 0;
        const workflowState =
          typeof event.payload.workflow_state === "string"
            ? (event.payload.workflow_state as WorkflowState)
            : state.workflowState;
        const activeTaskType =
          typeof event.payload.active_task_type === "string"
            ? event.payload.active_task_type
            : event.payload.active_task_type === null
            ? null
            : state.activeTaskType;
        return {
          eventStreamState: "connected",
          workflowState,
          activeTaskType,
          lastEventSequence: Math.max(state.lastEventSequence, payloadLastSequence),
          processingPhase: toProcessingPhaseFromWorkflow(workflowState, activeTaskType),
        };
      });
      return;
    case "media.processing.progress": {
      const stage = typeof event.payload.stage === "string" ? event.payload.stage : "scan";
      setState({
        isMediaProcessing: true,
        mediaStatusText: formatMediaEventMessage(stage, event.payload),
        processingPhase: mapMediaStageToPhase(stage),
        workflowState: "media_processing",
        activeTaskType: stage === "index" ? "index" : "ingest",
        lastEventSequence: nextSequence ?? getState().lastEventSequence,
      });
      return;
    }
    case "media.processing.completed":
      setState((state) => ({
        isMediaProcessing: false,
        mediaStatusText:
          typeof event.payload.message === "string" ? event.payload.message : state.mediaStatusText,
        workflowState: state.isThinking ? "chat_thinking" : "media_ready",
        activeTaskType: null,
        processingPhase: state.isThinking ? "chat_thinking" : "ready",
        lastEventSequence: nextSequence ?? state.lastEventSequence,
      }));
      return;
    case "workspace.chat.received":
      setState({
        isThinking: true,
        processingPhase: "chat_thinking",
        workflowState: "chat_thinking",
        activeTaskType: "chat",
        lastEventSequence: nextSequence ?? getState().lastEventSequence,
      });
      return;
    case "workspace.chat.ready":
      setState((state) => ({
        isThinking: false,
        workflowState:
          typeof event.payload.workflow_state === "string"
            ? (event.payload.workflow_state as WorkflowState)
            : "ready",
        activeTaskType: null,
        processingPhase: toProcessingPhaseFromWorkflow(
          typeof event.payload.workflow_state === "string"
            ? event.payload.workflow_state
            : "ready",
          null
        ),
        mediaStatusText:
          typeof event.payload.message === "string" ? event.payload.message : state.mediaStatusText,
        lastEventSequence: nextSequence ?? state.lastEventSequence,
      }));
      return;
    case "workspace.patch.ready": {
      const reasoningSummary =
        typeof event.payload.reasoning_summary === "string"
          ? event.payload.reasoning_summary
          : "AI returned a patch.";
      const rawOps = Array.isArray(event.payload.ops) ? event.payload.ops : [];
      const workflowState =
        typeof event.payload.workflow_state === "string"
          ? (event.payload.workflow_state as WorkflowState)
          : "ready";
      const decisionType =
        typeof event.payload.decision_type === "string"
          ? (event.payload.decision_type as DecisionType)
          : "UPDATE_PROJECT_CONTRACT";
      const assistantTurn: AssistantDecisionTurn = {
        id:
          typeof event.payload.turn_id === "string"
            ? event.payload.turn_id
            : event.event_id
            ? `assistant_event_${event.event_id}`
            : `assistant_event_${nextSequence ?? Date.now()}`,
        role: "assistant",
        type: "decision",
        decision_type: decisionType,
        reasoning_summary: reasoningSummary,
        ops: rawOps.filter((item): item is AgentOperation => typeof item === "object" && item !== null),
      };
      setState((state) => ({
        chatTurns: [...state.chatTurns, assistantTurn],
        isThinking: false,
        workflowState,
        activeTaskType: null,
        processingPhase: toProcessingPhaseFromWorkflow(workflowState, null),
        lastEventSequence: nextSequence ?? state.lastEventSequence,
      }));
      return;
    }
    case "notification":
    case "launchpad.project.initialized":
    default:
      return;
  }
}

async function runMediaPipeline(projectId: string, pendingPrompt?: string): Promise<void> {
  const setState = useWorkspaceStore.setState;
  const getState = useWorkspaceStore.getState;
  setState({
    isMediaProcessing: true,
    mediaStatusText: "视频处理中：正在切分镜头...",
    processingPhase: "media_processing",
    workflowState: "media_processing",
    activeTaskType: "ingest",
    lastError: null,
  });

  try {
    const ingest = await coreIngestProject(projectId);
    setState({
      assets: mapAssets(ingest.assets),
      clips: mapClips(ingest.clips),
      storyboard: buildStoryboardFromClips(ingest.clips),
      mediaStatusText: "视频处理中：正在向量化片段...",
      processingPhase: "indexing",
      workflowState: "media_processing",
      activeTaskType: "index",
    });

    const indexed = await coreUpsertClips({
      project_id: projectId,
      clips: ingest.clips,
    });

    const summaryTurn: AssistantDecisionTurn = {
      id: `assistant_${Date.now()}`,
      role: "assistant",
      type: "decision",
      decision_type: "UPDATE_PROJECT_CONTRACT",
      reasoning_summary: `素材处理完成，已切分 ${ingest.stats.clip_count} 个片段，向量化成功 ${indexed.indexed} 个。`,
      ops: [
        { op: "ingest_completed", note: "Ingest completed" },
        { op: "indexed_clips", note: `Indexed ${indexed.indexed} clips` },
      ],
    };

    setState((state) => ({
      chatTurns: [...state.chatTurns, summaryTurn],
      isMediaProcessing: false,
      mediaStatusText: null,
      processingPhase: "ready",
      workflowState: "ready",
      activeTaskType: null,
    }));

    const queued = pendingPrompt?.trim();
    if (queued) {
      setState({ pendingPrompt: null });
      await getState().sendChat(queued);
    }
  } catch (error) {
    setState({
      isMediaProcessing: false,
      mediaStatusText: null,
      processingPhase: "failed",
      workflowState: "failed",
      activeTaskType: null,
      lastError: toWorkspaceError("media_pipeline_failed", error),
    });
  }
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspaceId: null,
  workspaceName: null,
  assets: [],
  clips: [],
  storyboard: [],
  currentProject: null,
  chatTurns: [],
  isLoadingWorkspace: false,
  isMediaProcessing: false,
  mediaStatusText: null,
  isThinking: false,
  isExporting: false,
  exportResult: null,
  processingPhase: "idle",
  eventStreamState: "disconnected",
  reconnectState: "idle",
  workflowState: null,
  activeTaskType: null,
  lastEventSequence: 0,
  pendingPrompt: null,
  lastError: null,

  connectProjectEvents: (workspaceId) => {
    if (activeProjectSocket && activeProjectSocketId === workspaceId) {
      return;
    }

    if (activeProjectSocket) {
      closeManagedSocket(activeProjectSocket);
      activeProjectSocket = null;
      activeProjectSocketId = null;
    }

    set({ eventStreamState: "connecting" });
    const sessionId = getOrCreateSessionId(workspaceId);
    activeProjectSocket = createManagedProjectEventSocket(
      workspaceId,
      {
        sessionId,
        lastSequence: get().lastEventSequence,
        getLastSequence: () => useWorkspaceStore.getState().lastEventSequence,
      },
      {
        onEvent: applyCoreEvent,
        onReconnectStateChange: (reconnectState) => {
          set((state) => ({
            reconnectState,
            eventStreamState:
              reconnectState === "reconnecting"
                ? "connecting"
                : reconnectState === "max_attempts_reached"
                ? "disconnected"
                : state.eventStreamState,
          }));
          if (reconnectState === "max_attempts_reached") {
            activeProjectSocket = null;
            activeProjectSocketId = null;
          }
        },
        onOpen: () => {
          set({ eventStreamState: "connected", reconnectState: "idle" });
        },
        onClose: (event) => {
          const authFailed = event.code === 4400 || event.code === 4401 || event.code === 4403;
          set((state) => ({
            eventStreamState: state.reconnectState === "reconnecting" ? "connecting" : "disconnected",
            reconnectState: authFailed ? "idle" : state.reconnectState,
            lastError: authFailed
              ? {
                  code: "WS_AUTH_FAILED",
                  message: `websocket_closed_${event.code}`,
                }
              : state.lastError,
          }));
          if (authFailed) {
            activeProjectSocket = null;
            activeProjectSocketId = null;
          }
        },
        onError: () => {
          set((state) => ({
            eventStreamState: state.reconnectState === "reconnecting" ? "connecting" : "disconnected",
          }));
        },
      }
    );
    activeProjectSocketId = workspaceId;
  },

  disconnectProjectEvents: () => {
    if (activeProjectSocket) {
      closeManagedSocket(activeProjectSocket);
    }
    activeProjectSocket = null;
    activeProjectSocketId = null;
    set({ eventStreamState: "disconnected", reconnectState: "idle" });
  },

  initializeWorkspace: async (workspaceId, workspaceName) => {
    const shouldResetProject = get().workspaceId !== workspaceId;
    get().connectProjectEvents(workspaceId);
    set({
      workspaceId,
      workspaceName: workspaceName ?? get().workspaceName ?? workspaceId,
      isLoadingWorkspace: true,
      reconnectState: shouldResetProject ? "idle" : get().reconnectState,
      currentProject: shouldResetProject ? null : get().currentProject,
      workflowState: shouldResetProject ? null : get().workflowState,
      activeTaskType: shouldResetProject ? null : get().activeTaskType,
      lastError: null,
    });

    try {
      const detail = await coreGetProject(workspaceId);
      const mappedAssets = mapAssets(detail.assets);
      const mappedClips = mapClips(detail.clips);
      set({
        workspaceId: detail.project_id,
        workspaceName: detail.title,
        assets: mappedAssets,
        clips: mappedClips,
        workflowState: (detail.workflow_state as WorkflowState | undefined) ?? get().workflowState,
        activeTaskType: detail.active_task_type ?? null,
        lastEventSequence: detail.last_event_sequence ?? get().lastEventSequence,
        currentProject: get().currentProject,
        storyboard:
          get().storyboard.length > 0
            ? get().storyboard
            : buildStoryboardFromClips(detail.clips),
        isMediaProcessing: detail.active_task_type === "ingest" || detail.active_task_type === "index",
        processingPhase: toProcessingPhaseFromWorkflow(
          detail.workflow_state ?? get().workflowState,
          detail.active_task_type ?? null
        ),
      });
    } catch (error) {
      set({
        assets: [],
        clips: [],
        storyboard: [],
        currentProject: null,
        workflowState: null,
        activeTaskType: null,
        lastError: toWorkspaceError("load_workspace_failed", error),
      });
    } finally {
      set({ isLoadingWorkspace: false });
    }
  },

  bootstrapFromLaunch: async (input) => {
    const trimmedPrompt = input.prompt?.trim();
    get().connectProjectEvents(input.projectId);
    set({
      workspaceId: input.projectId,
      workspaceName: input.workspaceName,
      assets: [],
      clips: [],
      storyboard: [],
      currentProject: null,
      chatTurns: [],
      isThinking: false,
      isMediaProcessing: false,
      mediaStatusText: null,
      processingPhase: "idle",
      reconnectState: "idle",
      workflowState: input.hasMedia ? "media_ready" : "prompt_input_required",
      activeTaskType: null,
      lastEventSequence: 0,
      pendingPrompt: input.hasMedia ? trimmedPrompt ?? null : null,
      lastError: null,
    });

    await get().initializeWorkspace(input.projectId, input.workspaceName);

    if (input.hasMedia) {
      await runMediaPipeline(input.projectId, trimmedPrompt);
      return;
    }

    if (trimmedPrompt) {
      await get().sendChat(trimmedPrompt);
      return;
    }

    set({ processingPhase: "ready" });
  },

  uploadAssets: async (input) => {
    const workspaceId = get().workspaceId;
    if (!workspaceId) {
      set({
        lastError: {
          code: "WORKSPACE_NOT_READY",
          message: "workspace_not_ready",
        },
      });
      return;
    }

    set({ lastError: null });
    let media = normalizeMediaInput(input);
    if (!media && input?.shouldPickMedia) {
      media = await pickMediaFromSystem();
    }
    if (!media) {
      return;
    }

    try {
      if (media.folderPath) {
        await coreImportAssets(workspaceId, media.folderPath);
      } else if (media.files && media.files.length > 0) {
        await coreUploadAssets(workspaceId, media.files);
      }
      await get().initializeWorkspace(workspaceId, get().workspaceName ?? workspaceId);
      await runMediaPipeline(workspaceId, get().pendingPrompt ?? undefined);
    } catch (error) {
      set({
        lastError: toWorkspaceError("upload_assets_failed", error),
      });
    }
  },

  sendChat: async (prompt) => {
    const workspaceId = get().workspaceId;
    const trimmedPrompt = prompt.trim();
    if (!workspaceId || !trimmedPrompt) {
      return;
    }

    if (get().isMediaProcessing) {
      set({ pendingPrompt: trimmedPrompt });
      const queuedTurn: AssistantDecisionTurn = {
        id: `assistant_${Date.now()}`,
        role: "assistant",
        type: "decision",
        decision_type: "ASK_USER_CLARIFICATION",
        reasoning_summary: "素材还在处理中，完成后会自动执行你的指令。",
        ops: [{ op: "prompt_queued", note: "Prompt queued" }],
      };
      set((state) => ({
        chatTurns: [
          ...state.chatTurns,
          { id: `user_${Date.now()}`, role: "user", content: trimmedPrompt },
          queuedTurn,
        ],
      }));
      return;
    }

    const hasMedia = get().assets.length > 0;
    const userTurn: UserTurn = {
      id: `user_${Date.now()}`,
      role: "user",
      content: trimmedPrompt,
    };

    set((state) => ({
      chatTurns: [...state.chatTurns, userTurn],
      isThinking: true,
      processingPhase: "chat_thinking",
      workflowState: "chat_thinking",
      activeTaskType: "chat",
      lastError: null,
    }));

    try {
      const response = await coreChat({
        project_id: workspaceId,
        session_id: getOrCreateSessionId(workspaceId),
        message: trimmedPrompt,
        current_project: get().currentProject
          ? (JSON.parse(JSON.stringify(get().currentProject)) as Record<string, unknown>)
          : undefined,
        context: {
          has_media: hasMedia,
          clip_count: get().clips.length,
          asset_count: get().assets.length,
        },
      });

      const assistantTurn: AssistantDecisionTurn = {
        id: `assistant_${Date.now() + 1}`,
        role: "assistant",
        type: "decision",
        decision_type: response.decision_type,
        reasoning_summary: response.reasoning_summary,
        ops: response.ops,
      };

      set((state) => ({
        chatTurns:
          state.eventStreamState === "connected" ? state.chatTurns : [...state.chatTurns, assistantTurn],
        currentProject: response.project ?? state.currentProject,
        storyboard: mapStoryboardFromServer(response.storyboard_scenes, state.storyboard),
        isThinking: false,
        workflowState:
          response.decision_type === "ASK_USER_CLARIFICATION" && !hasMedia
            ? "awaiting_media"
            : "ready",
        activeTaskType: null,
        lastEventSequence:
          state.eventStreamState !== "connected" && typeof response.meta?.core_event_sequence === "number"
            ? Math.max(state.lastEventSequence, response.meta.core_event_sequence)
            : state.lastEventSequence,
        processingPhase: "ready",
      }));
    } catch (error) {
      set({
        isThinking: false,
        processingPhase: "failed",
        workflowState: "failed",
        activeTaskType: null,
        lastError: toWorkspaceError("send_chat_failed", error),
      });
    }
  },

  exportProject: async () => {
    const workspaceId = get().workspaceId;
    if (!workspaceId) {
      set({
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

    set({
      isExporting: true,
      exportResult: null,
      workflowState: "rendering",
      activeTaskType: "render",
      mediaStatusText: "正在渲染导出...",
      lastError: null,
    });

    try {
      const result = await coreRender({
        project_id: workspaceId,
        render_type: "export",
        format: "mp4",
        resolution: "original",
        codec: "h264",
      });

      set({
        isExporting: false,
        exportResult: result,
        workflowState: "ready",
        activeTaskType: null,
        mediaStatusText: null,
      });

      return result;
    } catch (error) {
      set({
        isExporting: false,
        exportResult: null,
        workflowState: "failed",
        activeTaskType: null,
        mediaStatusText: null,
        lastError: toWorkspaceError("export_failed", error),
      });
      return null;
    }
  },

  clearLastError: () => {
    set({ lastError: null });
  },
}));
