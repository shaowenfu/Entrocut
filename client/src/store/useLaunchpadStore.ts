import { create } from "zustand";

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
  | "SCHEMA_ERROR";

export interface LaunchpadError {
  code: ErrorCode;
  message: string;
  cause?: string;
}

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
  importLocalFolder: (folderPath?: string) => Promise<string | null>;
  createEmptyProject: () => Promise<string>;
  createProjectFromPrompt: (prompt: string, folderPath?: string) => Promise<string>;
  openWorkspace: (project: ProjectMeta) => void;
  clearActiveWorkspace: () => void;
  clearLastError: () => void;
}

interface ProjectsResponse {
  items: Array<{
    id: string;
    title: string;
    storage_type?: "cloud" | "local";
    last_active_text?: string;
    ai_status?: string;
    last_ai_edit?: string;
    thumbnail_class_name?: string;
  }>;
}

interface CreateProjectPayload {
  title?: string;
  source_folder_path?: string;
}

interface CreateProjectResponse {
  project_id: string;
  title?: string;
}

const REQUEST_TIMEOUT_MS = 3000;
const DEFAULT_CORE_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:8001";

function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function envBaseUrl(key: "VITE_CORE_BASE_URL" | "VITE_SERVER_BASE_URL", fallback: string): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const value = env[key]?.trim();
  return trimTrailingSlash(value && value.length > 0 ? value : fallback);
}

function getCoreBaseUrl(): string {
  return envBaseUrl("VITE_CORE_BASE_URL", DEFAULT_CORE_BASE_URL);
}

function getServerBaseUrl(): string {
  return envBaseUrl("VITE_SERVER_BASE_URL", DEFAULT_SERVER_BASE_URL);
}

function toLaunchpadError(code: ErrorCode, message: string, cause?: unknown): LaunchpadError {
  return {
    code,
    message,
    cause: cause instanceof Error ? cause.message : typeof cause === "string" ? cause : undefined,
  };
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw toLaunchpadError("HTTP_ERROR", `request_failed_${response.status}`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if ((error as LaunchpadError)?.code) {
      throw error;
    }
    throw toLaunchpadError("NETWORK_ERROR", "network_unreachable", error);
  } finally {
    window.clearTimeout(timer);
  }
}

function mapProject(item: ProjectsResponse["items"][number]): ProjectMeta {
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

async function coreListProjects(): Promise<ProjectMeta[]> {
  const data = await fetchJson<ProjectsResponse>(`${getCoreBaseUrl()}/api/v1/projects`, {
    method: "GET",
  });
  if (!Array.isArray(data.items)) {
    throw toLaunchpadError("SCHEMA_ERROR", "projects_items_invalid");
  }
  return data.items.map(mapProject);
}

async function coreCreateProject(payload: CreateProjectPayload): Promise<CreateProjectResponse> {
  return fetchJson<CreateProjectResponse>(`${getCoreBaseUrl()}/api/v1/projects`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

async function coreImportProject(folderPath: string): Promise<CreateProjectResponse> {
  return fetchJson<CreateProjectResponse>(`${getCoreBaseUrl()}/api/v1/projects/import`, {
    method: "POST",
    body: JSON.stringify({ folder_path: folderPath }),
  });
}

async function serverStartChat(projectId: string, prompt: string): Promise<void> {
  await fetchJson<{ ok?: boolean }>(`${getServerBaseUrl()}/api/v1/chat`, {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      message: prompt,
    }),
  });
}

async function pickFolderFromElectron(): Promise<string | null> {
  const bridge = window.electron;
  if (!bridge?.showOpenDirectory) {
    throw toLaunchpadError("BRIDGE_UNAVAILABLE", "electron_bridge_missing");
  }
  const pickedPath = await bridge.showOpenDirectory();
  if (!pickedPath) {
    return null;
  }
  return pickedPath;
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
      const projects = await coreListProjects();
      set({ recentProjects: projects });
    } catch (error) {
      set({
        recentProjects: [],
        lastError: (error as LaunchpadError) ?? toLaunchpadError("NETWORK_ERROR", "fetch_projects_failed"),
      });
    } finally {
      set({ isLoadingProjects: false });
    }
  },

  importLocalFolder: async (folderPath?: string) => {
    set({ isImporting: true, lastError: null });
    try {
      const pickedPath = folderPath ?? (await pickFolderFromElectron());
      if (!pickedPath) {
        return null;
      }
      const created = await coreImportProject(pickedPath);
      const workspaceName = created.title?.trim() || "Imported Workspace";
      set({
        activeWorkspaceId: created.project_id,
        activeWorkspaceName: workspaceName,
      });
      await get().fetchRecentProjects();
      return created.project_id;
    } catch (error) {
      set({
        lastError:
          (error as LaunchpadError) ?? toLaunchpadError("NETWORK_ERROR", "import_local_folder_failed", error),
      });
      return null;
    } finally {
      set({ isImporting: false });
    }
  },

  createEmptyProject: async () => {
    set({ isCreating: true, lastError: null, isThinking: false });
    try {
      const created = await coreCreateProject({ title: "Untitled Sequence" });
      set({
        activeWorkspaceId: created.project_id,
        activeWorkspaceName: created.title?.trim() || "Untitled Sequence",
      });
      await get().fetchRecentProjects();
      return created.project_id;
    } catch (error) {
      const appError =
        (error as LaunchpadError) ?? toLaunchpadError("NETWORK_ERROR", "create_empty_project_failed", error);
      set({ lastError: appError });
      throw appError;
    } finally {
      set({ isCreating: false });
    }
  },

  createProjectFromPrompt: async (prompt: string, folderPath?: string) => {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) {
      const appError = toLaunchpadError("INVALID_INPUT", "prompt_required");
      set({ lastError: appError });
      throw appError;
    }

    set({ isCreating: true, isThinking: true, lastError: null });
    try {
      const created = await coreCreateProject({
        title: trimmedPrompt.slice(0, 32),
        source_folder_path: folderPath,
      });

      set({
        activeWorkspaceId: created.project_id,
        activeWorkspaceName: created.title?.trim() || trimmedPrompt.slice(0, 32),
      });

      void serverStartChat(created.project_id, trimmedPrompt)
        .catch((error) => {
          set({
            lastError:
              (error as LaunchpadError) ??
              toLaunchpadError("NETWORK_ERROR", "start_chat_failed", error),
          });
        })
        .finally(() => {
          set({ isThinking: false });
        });

      await get().fetchRecentProjects();
      return created.project_id;
    } catch (error) {
      const appError =
        (error as LaunchpadError) ?? toLaunchpadError("NETWORK_ERROR", "create_project_from_prompt_failed", error);
      set({ lastError: appError, isThinking: false });
      throw appError;
    } finally {
      set({ isCreating: false });
    }
  },

  openWorkspace: (project: ProjectMeta) => {
    set({
      activeWorkspaceId: project.id,
      activeWorkspaceName: project.title,
      lastError: null,
    });
  },

  clearActiveWorkspace: () => {
    set({
      activeWorkspaceId: null,
      activeWorkspaceName: null,
    });
  },

  clearLastError: () => {
    set({ lastError: null });
  },
}));
