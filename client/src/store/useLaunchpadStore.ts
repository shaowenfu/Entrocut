import { create } from "zustand";
import {
  isElectronEnvironment,
  normalizeMediaInput,
  pickMediaByMode,
  type MediaPickInput,
} from "../services/electronBridge";
import {
  createProject,
  listProjects,
  toMediaReference,
  type CoreProject,
} from "../services/coreClient";
import { registerProjectMediaSources } from "../services/localMediaRegistry";
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

export type LoadState = "idle" | "loading" | "ready" | "failed";
export type SystemStatus = "connecting" | "ready" | "error";
export type CreateState = "idle" | "creating" | "failed";
export type ImportState = "idle" | "picking_media" | "importing" | "failed";
export type NavigationState = "idle" | "entering_workspace" | "failed";

interface StartLaunchInput extends MediaPickInput {
  prompt?: string;
  shouldPickMedia?: boolean;
}

type ImportMediaInput = MediaPickInput;

type LaunchpadEvent =
  | { type: "PROJECTS_LOAD_STARTED" }
  | { type: "PROJECTS_LOAD_SUCCEEDED"; projects: ProjectMeta[] }
  | { type: "PROJECTS_LOAD_FAILED"; error: LaunchpadError }
  | { type: "SYSTEM_CHECK_STARTED" }
  | { type: "SYSTEM_CHECK_SUCCEEDED" }
  | { type: "SYSTEM_CHECK_FAILED" }
  | { type: "CREATE_STARTED" }
  | { type: "CREATE_SUCCEEDED"; projectId: string; projectName: string }
  | { type: "CREATE_FAILED"; error: LaunchpadError; duringImport?: boolean }
  | { type: "MEDIA_PICK_STARTED" }
  | { type: "MEDIA_PICK_CANCELLED" }
  | { type: "MEDIA_PICK_SUCCEEDED" }
  | { type: "IMPORT_STARTED" }
  | { type: "IMPORT_FAILED"; error: LaunchpadError }
  | { type: "NAVIGATION_STARTED" }
  | { type: "NAVIGATION_SUCCEEDED" }
  | { type: "NAVIGATION_FAILED"; error: LaunchpadError }
  | { type: "CLEAR_ERROR" };

interface LaunchpadState {
  recentProjects: ProjectMeta[];
  activeWorkspaceId: string | null;
  activeWorkspaceName: string | null;
  projectsLoadState: LoadState;
  systemStatus: SystemStatus;
  createState: CreateState;
  importState: ImportState;
  navigationState: NavigationState;
  lastError: LaunchpadError | null;
  fetchRecentProjects: () => Promise<void>;
  startWorkspaceFromLaunchpad: (input?: StartLaunchInput) => Promise<string | null>;
  pickMediaAndStartWorkspace: (prompt?: string) => Promise<string | null>;
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

function formatLastActiveText(updatedAt: string): string {
  const updatedAtMs = Date.parse(updatedAt);
  if (Number.isNaN(updatedAtMs)) {
    return "Updated recently";
  }
  const diffMinutes = Math.max(1, Math.round((Date.now() - updatedAtMs) / 60000));
  if (diffMinutes < 60) {
    return `${diffMinutes} min ago`;
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours} hr ago`;
  }
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays} day${diffDays > 1 ? "s" : ""} ago`;
}

function projectThumbnailClass(projectId: string): string {
  const variants = [
    "gradient-peach",
    "gradient-lime",
    "gradient-sky",
    "gradient-rose",
  ] as const;
  const index = projectId.length % variants.length;
  return variants[index];
}

function mapProjectMeta(project: CoreProject): ProjectMeta {
  return {
    id: project.id,
    title: project.title,
    thumbnailClassName: projectThumbnailClass(project.id),
    storageType: "local",
    lastActiveText: formatLastActiveText(project.updated_at),
    aiStatus: project.workflow_state,
    lastAiEdit: `workflow=${project.workflow_state}`,
  };
}

function reduceLaunchpadState(
  state: Pick<
    LaunchpadState,
    | "recentProjects"
    | "activeWorkspaceId"
    | "activeWorkspaceName"
    | "projectsLoadState"
    | "systemStatus"
    | "createState"
    | "importState"
    | "navigationState"
    | "lastError"
  >,
  event: LaunchpadEvent
): Partial<LaunchpadState> {
  switch (event.type) {
    case "PROJECTS_LOAD_STARTED":
      return {
        projectsLoadState: "loading",
        lastError: null,
      };
    case "PROJECTS_LOAD_SUCCEEDED":
      return {
        recentProjects: event.projects,
        projectsLoadState: "ready",
      };
    case "PROJECTS_LOAD_FAILED":
      return {
        recentProjects: [],
        projectsLoadState: "failed",
        lastError: event.error,
      };
    case "SYSTEM_CHECK_STARTED":
      return {
        systemStatus: "connecting",
      };
    case "SYSTEM_CHECK_SUCCEEDED":
      return {
        systemStatus: "ready",
      };
    case "SYSTEM_CHECK_FAILED":
      return {
        systemStatus: "error",
      };
    case "CREATE_STARTED":
      return {
        createState: "creating",
        lastError: null,
      };
    case "CREATE_SUCCEEDED":
      return {
        createState: "idle",
        importState: "idle",
        activeWorkspaceId: event.projectId,
        activeWorkspaceName: event.projectName,
      };
    case "CREATE_FAILED":
      return {
        createState: "failed",
        importState: event.duringImport ? "failed" : state.importState,
        lastError: event.error,
      };
    case "MEDIA_PICK_STARTED":
      return {
        importState: "picking_media",
        lastError: null,
      };
    case "MEDIA_PICK_CANCELLED":
      return {
        importState: "idle",
      };
    case "MEDIA_PICK_SUCCEEDED":
      return {
        importState: "importing",
      };
    case "IMPORT_STARTED":
      return {
        importState: "importing",
        lastError: null,
      };
    case "IMPORT_FAILED":
      return {
        importState: "failed",
        lastError: event.error,
      };
    case "NAVIGATION_STARTED":
      return {
        navigationState: "entering_workspace",
      };
    case "NAVIGATION_SUCCEEDED":
      return {
        navigationState: "idle",
      };
    case "NAVIGATION_FAILED":
      return {
        navigationState: "failed",
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

export const useLaunchpadStore = create<LaunchpadState>((set, get) => {
  const dispatch = (event: LaunchpadEvent) => {
    set((state) => reduceLaunchpadState(state, event));
  };

  const navigateToWorkspace = async (input: {
    projectId: string;
    workspaceName: string;
    prompt?: string;
    hasMedia: boolean;
  }): Promise<void> => {
    dispatch({ type: "NAVIGATION_STARTED" });
    try {
      await get().fetchRecentProjects();
      await useWorkspaceStore.getState().bootstrapFromLaunch({
        projectId: input.projectId,
        workspaceName: input.workspaceName,
        prompt: input.prompt,
        hasMedia: input.hasMedia,
      });
      dispatch({ type: "NAVIGATION_SUCCEEDED" });
    } catch (error) {
      dispatch({
        type: "NAVIGATION_FAILED",
        error: toLaunchpadErrorFromUnknown(error, "CORE_REQUEST_FAILED", "navigation_to_workspace_failed"),
      });
      throw error;
    }
  };

  return {
    recentProjects: [],
    activeWorkspaceId: null,
    activeWorkspaceName: null,
    projectsLoadState: "idle",
    systemStatus: "connecting",
    createState: "idle",
    importState: "idle",
    navigationState: "idle",
    lastError: null,

    fetchRecentProjects: async () => {
      dispatch({ type: "SYSTEM_CHECK_STARTED" });
      dispatch({ type: "PROJECTS_LOAD_STARTED" });
      try {
        const response = await listProjects();
        dispatch({ type: "SYSTEM_CHECK_SUCCEEDED" });
        dispatch({
          type: "PROJECTS_LOAD_SUCCEEDED",
          projects: response.projects.map(mapProjectMeta),
        });
      } catch (error) {
        dispatch({ type: "SYSTEM_CHECK_FAILED" });
        dispatch({
          type: "PROJECTS_LOAD_FAILED",
          error: toLaunchpadErrorFromUnknown(error, "CORE_REQUEST_FAILED", "fetch_projects_failed"),
        });
      }
    },

    startWorkspaceFromLaunchpad: async (input) => {
      const trimmedPrompt = input?.prompt?.trim() ?? "";
      let media = normalizeMediaInput(input);
      const needsMediaPick = !media && input?.shouldPickMedia;
      const duringImport = needsMediaPick || Boolean(media);

      if (needsMediaPick) {
        dispatch({ type: "MEDIA_PICK_STARTED" });
        const mode = isElectronEnvironment() ? "electron-folder" : "browser-files";
        media = await pickMediaByMode(mode);
        if (!media) {
          dispatch({ type: "MEDIA_PICK_CANCELLED" });
          return null;
        }
        dispatch({ type: "MEDIA_PICK_SUCCEEDED" });
      } else if (media) {
        dispatch({ type: "IMPORT_STARTED" });
      } else {
        dispatch({ type: "CREATE_STARTED" });
      }

      try {
        const hasMedia = Boolean(media?.folderPath || (media?.files && media.files.length > 0));
        if (!hasMedia && !trimmedPrompt) {
          const appError = toLaunchpadError("INVALID_INPUT", "prompt_or_media_required");
          dispatch({
            type: duringImport ? "IMPORT_FAILED" : "CREATE_FAILED",
            error: appError,
            ...(duringImport ? {} : { duringImport: false }),
          } as LaunchpadEvent);
          return null;
        }

        if (duringImport && !needsMediaPick) {
          dispatch({ type: "IMPORT_STARTED" });
        }
        if (!duringImport) {
          dispatch({ type: "CREATE_STARTED" });
        }

        const created = await createProject({
          prompt: trimmedPrompt || undefined,
          media: toMediaReference(media),
          title: !hasMedia ? trimmedPrompt.slice(0, 32) || "Untitled Project" : undefined,
        });

        dispatch({
          type: "CREATE_SUCCEEDED",
          projectId: created.project.id,
          projectName: created.project.title,
        });
        registerProjectMediaSources(created.project.id, media);

        await navigateToWorkspace({
          projectId: created.project.id,
          workspaceName: created.project.title,
          prompt: trimmedPrompt || undefined,
          hasMedia,
        });
        return created.project.id;
      } catch (error) {
        const appError = toLaunchpadErrorFromUnknown(
          error,
          "CORE_REQUEST_FAILED",
          "start_workspace_from_launchpad_failed"
        );
        if (duringImport) {
          dispatch({ type: "IMPORT_FAILED", error: appError });
        } else {
          dispatch({ type: "CREATE_FAILED", error: appError, duringImport: false });
        }
        return null;
      }
    },

    pickMediaAndStartWorkspace: async (prompt) => {
      return get().startWorkspaceFromLaunchpad({
        prompt,
        shouldPickMedia: true,
      });
    },

    importLocalFolder: async (input) => {
      return get().startWorkspaceFromLaunchpad({
        ...input,
        shouldPickMedia: !input?.folderPath && !(input?.files && input.files.length > 0),
      });
    },

    createEmptyProject: async () => {
      dispatch({ type: "CREATE_STARTED" });
      try {
        const created = await createProject({ title: "Untitled Project" });
        dispatch({
          type: "CREATE_SUCCEEDED",
          projectId: created.project.id,
          projectName: created.project.title,
        });
        await navigateToWorkspace({
          projectId: created.project.id,
          workspaceName: created.project.title,
          hasMedia: false,
        });
        return created.project.id;
      } catch (error) {
        const appError = toLaunchpadErrorFromUnknown(
          error,
          "CORE_REQUEST_FAILED",
          "create_empty_project_failed"
        );
        dispatch({ type: "CREATE_FAILED", error: appError, duringImport: false });
        throw appError;
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
        dispatch({ type: "CREATE_FAILED", error: appError, duringImport: false });
        throw appError;
      }
      return createdId;
    },

    openWorkspace: (project) => {
      dispatch({
        type: "CREATE_SUCCEEDED",
        projectId: project.id,
        projectName: project.title,
      });
      dispatch({ type: "NAVIGATION_STARTED" });
      dispatch({ type: "NAVIGATION_SUCCEEDED" });
    },

    clearActiveWorkspace: () => {
      useWorkspaceStore.getState().disconnectProjectEvents();
      set({
        activeWorkspaceId: null,
        activeWorkspaceName: null,
        navigationState: "idle",
      });
    },

    clearLastError: () => {
      dispatch({ type: "CLEAR_ERROR" });
    },
  };
});
