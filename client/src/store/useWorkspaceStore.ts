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

interface WorkspaceState {
  workspaceId: string | null;
  workspaceName: string | null;
  assets: WorkspaceAssetItem[];
  clips: WorkspaceClipItem[];
  storyboard: StoryboardScene[];
  currentProject: Record<string, unknown> | null;
  chatTurns: ChatTurn[];
  isLoadingWorkspace: boolean;
  isMediaProcessing: boolean;
  mediaStatusText: string | null;
  isThinking: boolean;
  isExporting: boolean;
  exportResult: ExportResult | null;
  processingPhase: ProcessingPhase;
  eventStreamState: "disconnected" | "connecting" | "connected";
  reconnectState: "idle" | "reconnecting" | "max_attempts_reached";
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
  exportProject: () => Promise<ExportResult | null>;
  clearLastError: () => void;
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

function applyRecord(record: PrototypeProjectRecord): Partial<WorkspaceState> {
  return {
    workspaceId: record.id,
    workspaceName: record.title,
    assets: mapAssets(record.assets),
    clips: mapClips(record.clips),
    storyboard: mapStoryboard(record.storyboard),
    chatTurns: mapTurns(record.chatTurns),
    currentProject: buildCurrentProject(record),
    isLoadingWorkspace: false,
    isMediaProcessing: false,
    mediaStatusText: null,
    isThinking: false,
    processingPhase: "ready",
    workflowState: record.assets.length > 0 ? "ready" : "awaiting_media",
    activeTaskType: null,
    eventStreamState: "connected",
    reconnectState: "idle",
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
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
    void workspaceId;
    set({ eventStreamState: "connected", reconnectState: "idle" });
  },

  disconnectProjectEvents: () => {
    set({ eventStreamState: "disconnected", reconnectState: "idle" });
  },

  initializeWorkspace: async (workspaceId, workspaceName) => {
    get().connectProjectEvents(workspaceId);
    set({
      isLoadingWorkspace: true,
      lastError: null,
    });

    try {
      const record = getPrototypeProject(workspaceId);
      if (!record) {
        throw new Error("prototype_project_not_found");
      }
      set({
        ...applyRecord(record),
        workspaceName: workspaceName ?? record.title,
        lastEventSequence: Date.now(),
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
      pendingPrompt: trimmedPrompt ?? null,
      lastError: null,
    });

    await get().initializeWorkspace(input.projectId, input.workspaceName);

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
      set({
        isMediaProcessing: true,
        mediaStatusText: "正在刷新 prototype 素材示意...",
        processingPhase: "media_processing",
        workflowState: "media_processing",
        activeTaskType: "ingest",
        lastError: null,
      });
      await sleep(220);
      const updated = addPrototypeAssets(workspaceId, media);
      if (!updated) {
        throw new Error("prototype_project_not_found");
      }
      set({
        ...applyRecord(updated),
        lastEventSequence: Date.now(),
      });
      const queuedPrompt = get().pendingPrompt?.trim();
      if (queuedPrompt) {
        set({ pendingPrompt: null });
        await get().sendChat(queuedPrompt);
      }
    } catch (error) {
      set({
        isMediaProcessing: false,
        mediaStatusText: null,
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
      set((state) => ({
        chatTurns: [
          ...state.chatTurns,
          { id: `user_${Date.now()}`, role: "user", content: trimmedPrompt },
          {
            id: `assistant_${Date.now()}`,
            role: "assistant",
            type: "decision",
            decision_type: "ASK_USER_CLARIFICATION",
            reasoning_summary: "素材示意还在刷新，完成后会自动应用这条指令。",
            ops: [{ op: "prompt_queued", note: "Queued in prototype mode" }],
          },
        ],
      }));
      return;
    }

    const hasMedia = get().assets.length > 0;
    set((state) => ({
      chatTurns: [...state.chatTurns, { id: `user_${Date.now()}`, role: "user", content: trimmedPrompt }],
      isThinking: true,
      processingPhase: "chat_thinking",
      workflowState: "chat_thinking",
      activeTaskType: "chat",
      lastError: null,
    }));

    try {
      await sleep(320);
      const updated = applyPrototypePrompt(workspaceId, trimmedPrompt);
      if (!updated) {
        throw new Error("prototype_project_not_found");
      }
      set({
        ...applyRecord(updated),
        isThinking: false,
        workflowState: hasMedia ? "ready" : "awaiting_media",
        activeTaskType: null,
        processingPhase: toProcessingPhaseFromWorkflow(hasMedia ? "ready" : "awaiting_media", null),
        lastEventSequence: Date.now(),
      });
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
      mediaStatusText: "正在生成 prototype 导出路径...",
      lastError: null,
    });

    try {
      await sleep(280);
      const result = exportPrototypeProject(workspaceId);
      if (!result) {
        throw new Error("prototype_project_not_found");
      }

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
