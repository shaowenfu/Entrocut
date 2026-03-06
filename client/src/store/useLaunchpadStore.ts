import { create } from "zustand";
import {
  coreCreateProject,
  coreImportProject,
  coreListProjects,
  coreUploadProject,
  type CoreProjectMetaDTO,
} from "../services/coreApi";
import {
  normalizeMediaInput,
  pickMediaFromSystem,
  type MediaPickInput,
} from "../services/electronBridge";
import { useWorkspaceStore } from "./useWorkspaceStore";

export interface ProjectMeta {
  id: string;
  title: string;
  thumbnailClassName: string;
  storageType: "cloud" | "local";
  lastActiveText: string;
  aiStatus: string;
  lastAiEdit: string;
}

type ErrorCode =
  | "BRIDGE_UNAVAILABLE"
  | "USER_CANCELLED"
  | "INVALID_INPUT"
  | "HTTP_ERROR"
  | "NETWORK_ERROR"
  | "SCHEMA_ERROR"
  | "AUTH_TOKEN_MISSING"
  | string;

export interface LaunchpadError {
  code: ErrorCode;
  message: string;
  cause?: string;
  requestId?: string;
}

interface StartLaunchInput extends MediaPickInput {
  prompt?: string;
  shouldPickMedia?: boolean;
}

type ImportMediaInput = MediaPickInput;

interface LaunchpadState {
  recentProjects: ProjectMeta[];
  activeWorkspaceId: string | null;
  activeWorkspaceName: string | null;
  isLoadingProjects: boolean;
  isImporting: boolean;
  isCreating: boolean;
  isThinking: boolean;
  lastError: LaunchpadError | null;
  fetchRecentProjects: () => Promise<void>;
  startWorkspaceFromLaunchpad: (input?: StartLaunchInput) => Promise<string | null>;
  importLocalFolder: (input?: ImportMediaInput) => Promise<string | null>;
  createEmptyProject: () => Promise<string>;
  createProjectFromPrompt: (prompt: string, folderPath?: string) => Promise<string>;
  openWorkspace: (project: ProjectMeta) => void;
  clearActiveWorkspace: () => void;
  clearLastError: () => void;
}

function toLaunchpadError(code: ErrorCode, message: string, cause?: unknown): LaunchpadError {
  return {
    code,
    message,
    cause: cause instanceof Error ? cause.message : typeof cause === "string" ? cause : undefined,
  };
}

function toLaunchpadErrorFromUnknown(
  error: unknown,
  fallbackCode: ErrorCode,
  fallbackMessage: string
): LaunchpadError {
  if (error && typeof error === "object") {
    const maybe = error as {
      code?: string;
      message?: string;
      cause?: string;
      requestId?: string;
      request_id?: string;
    };
    if (typeof maybe.code === "string" && typeof maybe.message === "string") {
      return {
        code: maybe.code,
        message: maybe.message,
        cause: maybe.cause,
        requestId:
          typeof maybe.requestId === "string"
            ? maybe.requestId
            : typeof maybe.request_id === "string"
            ? maybe.request_id
            : undefined,
      };
    }
  }
  return toLaunchpadError(fallbackCode, fallbackMessage, error);
}

function mapProject(item: CoreProjectMetaDTO): ProjectMeta {
  return {
    id: item.id,
    title: item.title,
    thumbnailClassName: item.thumbnail_class_name ?? "launch-thumb-zinc",
    storageType: item.storage_type ?? "local",
    lastActiveText: item.last_active_text ?? "unknown",
    aiStatus: item.ai_status ?? "Unknown",
    lastAiEdit: item.last_ai_edit ?? "None",
  };
}

export const useLaunchpadStore = create<LaunchpadState>((set, get) => ({
  recentProjects: [],
  activeWorkspaceId: null,
  activeWorkspaceName: null,
  isLoadingProjects: false,
  isImporting: false,
  isCreating: false,
  isThinking: false,
  lastError: null,

  fetchRecentProjects: async () => {
    set({ isLoadingProjects: true, lastError: null });
    try {
      const data = await coreListProjects();
      if (!Array.isArray(data.items)) {
        throw toLaunchpadError("SCHEMA_ERROR", "projects_items_invalid");
      }
      set({ recentProjects: data.items.map(mapProject) });
    } catch (error) {
      set({
        recentProjects: [],
        lastError: toLaunchpadErrorFromUnknown(error, "NETWORK_ERROR", "fetch_projects_failed"),
      });
    } finally {
      set({ isLoadingProjects: false });
    }
  },

  startWorkspaceFromLaunchpad: async (input) => {
    set({ isCreating: true, isImporting: true, lastError: null });
    try {
      const trimmedPrompt = input?.prompt?.trim() ?? "";
      let media = normalizeMediaInput(input);
      if (!media && input?.shouldPickMedia) {
        media = await pickMediaFromSystem();
        if (!media) {
          return null;
        }
      }

      const hasMedia = Boolean(media?.folderPath || (media?.files && media.files.length > 0));
      if (!hasMedia && !trimmedPrompt) {
        const appError = toLaunchpadError("INVALID_INPUT", "prompt_or_media_required");
        set({ lastError: appError });
        return null;
      }

      let created: { project_id: string; title: string };
      if (hasMedia && media?.folderPath) {
        created = await coreImportProject(media.folderPath);
      } else if (hasMedia && media?.files && media.files.length > 0) {
        created = await coreUploadProject(media.files);
      } else {
        created = await coreCreateProject({
          title: trimmedPrompt.slice(0, 32) || "Untitled Sequence",
        });
      }

      const workspaceName = created.title?.trim() || "Untitled Sequence";
      set({
        activeWorkspaceId: created.project_id,
        activeWorkspaceName: workspaceName,
      });

      await get().fetchRecentProjects();
      void useWorkspaceStore.getState().bootstrapFromLaunch({
        projectId: created.project_id,
        workspaceName,
        prompt: trimmedPrompt || undefined,
        hasMedia,
      });
      return created.project_id;
    } catch (error) {
      set({
        lastError: toLaunchpadErrorFromUnknown(
          error,
          "NETWORK_ERROR",
          "start_workspace_from_launchpad_failed"
        ),
      });
      return null;
    } finally {
      set({ isCreating: false, isImporting: false, isThinking: false });
    }
  },

  importLocalFolder: async (input) => {
    return get().startWorkspaceFromLaunchpad({
      ...input,
      shouldPickMedia: !input?.folderPath && !(input?.files && input.files.length > 0),
    });
  },

  createEmptyProject: async () => {
    set({ isCreating: true, lastError: null, isThinking: false });
    try {
      const created = await coreCreateProject({ title: "Untitled Sequence" });
      const workspaceName = created.title?.trim() || "Untitled Sequence";
      set({
        activeWorkspaceId: created.project_id,
        activeWorkspaceName: workspaceName,
      });
      await get().fetchRecentProjects();
      void useWorkspaceStore.getState().bootstrapFromLaunch({
        projectId: created.project_id,
        workspaceName,
        hasMedia: false,
      });
      return created.project_id;
    } catch (error) {
      const appError = toLaunchpadErrorFromUnknown(
        error,
        "NETWORK_ERROR",
        "create_empty_project_failed"
      );
      set({ lastError: appError });
      throw appError;
    } finally {
      set({ isCreating: false });
    }
  },

  createProjectFromPrompt: async (prompt, folderPath) => {
    const createdId = await get().startWorkspaceFromLaunchpad({
      prompt,
      folderPath,
      shouldPickMedia: false,
    });
    if (!createdId) {
      const appError = toLaunchpadError("INVALID_INPUT", "create_project_from_prompt_failed");
      set({ lastError: appError });
      throw appError;
    }
    return createdId;
  },

  openWorkspace: (project) => {
    set({
      activeWorkspaceId: project.id,
      activeWorkspaceName: project.title,
      lastError: null,
    });
    void useWorkspaceStore.getState().initializeWorkspace(project.id, project.title);
  },

  clearActiveWorkspace: () => {
    useWorkspaceStore.getState().disconnectProjectEvents();
    set({
      activeWorkspaceId: null,
      activeWorkspaceName: null,
      isThinking: false,
    });
  },

  clearLastError: () => {
    set({ lastError: null });
  },
}));
