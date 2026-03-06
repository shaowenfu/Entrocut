import { create } from "zustand";
import {
  coreGetProject,
  coreImportAssets,
  coreIngestProject,
  coreUploadAssets,
  type CoreAssetDTO,
  type CoreClipDTO,
} from "../services/coreApi";
import {
  normalizeMediaInput,
  pickMediaFromSystem,
  type MediaPickInput,
} from "../services/electronBridge";
import { serverChat, serverUpsertClips, type DecisionType } from "../services/serverApi";
import { getOrCreateSessionId } from "../utils/session";
import type { AgentOperation, EntroVideoProject } from "../contracts/contract";

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
  processingPhase: ProcessingPhase;
  pendingPrompt: string | null;
  lastError: WorkspaceError | null;
  initializeWorkspace: (workspaceId: string, workspaceName?: string) => Promise<void>;
  bootstrapFromLaunch: (input: BootstrapInput) => Promise<void>;
  uploadAssets: (input?: UploadAssetsInput) => Promise<void>;
  sendChat: (prompt: string) => Promise<void>;
  clearLastError: () => void;
}

const CLIP_THUMBS = ["thumb-blue", "thumb-indigo", "thumb-purple", "thumb-teal"] as const;
const SCENE_STYLES = [
  { colorClass: "scene-blue", bgClass: "scene-bg-blue" },
  { colorClass: "scene-indigo", bgClass: "scene-bg-indigo" },
  { colorClass: "scene-purple", bgClass: "scene-bg-purple" },
  { colorClass: "scene-cyan", bgClass: "scene-bg-cyan" },
] as const;
const NO_MEDIA_PROMPT_HINT = "当前没有可用素材，请先引导用户上传视频并给出具体下一步。";

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

async function runMediaPipeline(projectId: string, pendingPrompt?: string): Promise<void> {
  const setState = useWorkspaceStore.setState;
  const getState = useWorkspaceStore.getState;
  setState({
    isMediaProcessing: true,
    mediaStatusText: "视频处理中：正在切分镜头...",
    processingPhase: "media_processing",
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
    });

    const indexed = await serverUpsertClips({
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
  processingPhase: "idle",
  pendingPrompt: null,
  lastError: null,

  initializeWorkspace: async (workspaceId, workspaceName) => {
    const shouldResetProject = get().workspaceId !== workspaceId;
    set({
      workspaceId,
      workspaceName: workspaceName ?? get().workspaceName ?? workspaceId,
      isLoadingWorkspace: true,
      currentProject: shouldResetProject ? null : get().currentProject,
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
        currentProject: get().currentProject,
        storyboard:
          get().storyboard.length > 0
            ? get().storyboard
            : buildStoryboardFromClips(detail.clips),
      });
    } catch (error) {
      set({
        assets: [],
        clips: [],
        storyboard: [],
        currentProject: null,
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
    const composedPrompt = hasMedia
      ? trimmedPrompt
      : `${trimmedPrompt}\n\n[system]\n${NO_MEDIA_PROMPT_HINT}`;
    const userTurn: UserTurn = {
      id: `user_${Date.now()}`,
      role: "user",
      content: trimmedPrompt,
    };

    set((state) => ({
      chatTurns: [...state.chatTurns, userTurn],
      isThinking: true,
      processingPhase: "chat_thinking",
      lastError: null,
    }));

    try {
      const response = await serverChat({
        project_id: workspaceId,
        session_id: getOrCreateSessionId(workspaceId),
        message: composedPrompt,
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
        chatTurns: [...state.chatTurns, assistantTurn],
        currentProject: response.project ?? state.currentProject,
        storyboard: mapStoryboardFromServer(response.storyboard_scenes, state.storyboard),
        isThinking: false,
        processingPhase: "ready",
      }));
    } catch (error) {
      set({
        isThinking: false,
        processingPhase: "failed",
        lastError: toWorkspaceError("send_chat_failed", error),
      });
    }
  },

  clearLastError: () => {
    set({ lastError: null });
  },
}));
