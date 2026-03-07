import { create } from "zustand";
import { normalizeMediaInput, pickMediaFromSystem, type MediaPickInput } from "../services/electronBridge";
import {
  createEmptyPrototypeProject,
  createPrototypeProject,
  listPrototypeProjects,
} from "../mocks/prototypeWorkspace";
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
  | "PROTOTYPE_ERROR"
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
      await Promise.resolve();
      set({ recentProjects: listPrototypeProjects() });
    } catch (error) {
      set({
        recentProjects: [],
        lastError: toLaunchpadErrorFromUnknown(error, "PROTOTYPE_ERROR", "fetch_projects_failed"),
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

      const created = createPrototypeProject({
        prompt: trimmedPrompt || undefined,
        folderPath: media?.folderPath,
        files: media?.files,
        title: !hasMedia ? trimmedPrompt.slice(0, 32) || "Untitled Prototype" : undefined,
      });

      set({
        activeWorkspaceId: created.id,
        activeWorkspaceName: created.title,
      });

      await get().fetchRecentProjects();
      void useWorkspaceStore.getState().bootstrapFromLaunch({
        projectId: created.id,
        workspaceName: created.title,
        prompt: trimmedPrompt || undefined,
        hasMedia,
      });
      return created.id;
    } catch (error) {
      set({
        lastError: toLaunchpadErrorFromUnknown(
          error,
          "PROTOTYPE_ERROR",
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
      const created = createEmptyPrototypeProject("Untitled Prototype");
      set({
        activeWorkspaceId: created.id,
        activeWorkspaceName: created.title,
      });
      await get().fetchRecentProjects();
      void useWorkspaceStore.getState().bootstrapFromLaunch({
        projectId: created.id,
        workspaceName: created.title,
        hasMedia: false,
      });
      return created.id;
    } catch (error) {
      const appError = toLaunchpadErrorFromUnknown(
        error,
        "PROTOTYPE_ERROR",
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
  },

  clearActiveWorkspace: () => {
    useWorkspaceStore.getState().disconnectProjectEvents();
    set({ activeWorkspaceId: null, activeWorkspaceName: null });
  },

  clearLastError: () => {
    set({ lastError: null });
  },
}));
