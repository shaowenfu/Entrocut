export interface CoreProjectMetaDTO {
  id: string;
  title: string;
  storage_type?: "cloud" | "local";
  last_active_text?: string;
  ai_status?: string;
  last_ai_edit?: string;
  thumbnail_class_name?: string;
}

export interface CoreAssetDTO {
  asset_id: string;
  name: string;
  duration_ms: number;
  type: "video" | "audio";
}

export interface CoreClipDTO {
  clip_id: string;
  asset_id: string;
  start_ms: number;
  end_ms: number;
  score: number;
  description: string;
}

export interface CoreProjectDetailDTO {
  project_id: string;
  title: string;
  ai_status: string;
  last_ai_edit: string;
  assets: CoreAssetDTO[];
  clips: CoreClipDTO[];
}

export interface CoreIngestResponse {
  project_id: string;
  assets: CoreAssetDTO[];
  clips: CoreClipDTO[];
  stats: {
    clip_count: number;
    processing_ms: number;
  };
}

export interface CoreCreateProjectPayload {
  title?: string;
  source_folder_path?: string;
}

export interface CoreCreateProjectResponse {
  project_id: string;
  title: string;
}

export interface CoreListProjectsResponse {
  items: CoreProjectMetaDTO[];
}

interface CoreAddAssetsResponse {
  project_id: string;
  added_count: number;
  total_assets: number;
}

export interface AppHttpError {
  code: "INVALID_INPUT" | "HTTP_ERROR" | "NETWORK_ERROR" | "SCHEMA_ERROR";
  message: string;
  cause?: string;
}

const REQUEST_TIMEOUT_MS = 5000;
const DEFAULT_CORE_BASE_URL = "http://127.0.0.1:8000";

function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function envBaseUrl(key: "VITE_CORE_BASE_URL", fallback: string): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const value = env[key]?.trim();
  return trimTrailingSlash(value && value.length > 0 ? value : fallback);
}

export function getCoreBaseUrl(): string {
  return envBaseUrl("VITE_CORE_BASE_URL", DEFAULT_CORE_BASE_URL);
}

function toHttpError(
  code: AppHttpError["code"],
  message: string,
  cause?: unknown
): AppHttpError {
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
      throw toHttpError("HTTP_ERROR", `request_failed_${response.status}`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if ((error as AppHttpError)?.code) {
      throw error;
    }
    throw toHttpError("NETWORK_ERROR", "network_unreachable", error);
  } finally {
    window.clearTimeout(timer);
  }
}

async function fetchFormData<T>(url: string, formData: FormData): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
    if (!response.ok) {
      throw toHttpError("HTTP_ERROR", `request_failed_${response.status}`);
    }
    return (await response.json()) as T;
  } catch (error) {
    if ((error as AppHttpError)?.code) {
      throw error;
    }
    throw toHttpError("NETWORK_ERROR", "network_unreachable", error);
  } finally {
    window.clearTimeout(timer);
  }
}

export async function coreListProjects(): Promise<CoreListProjectsResponse> {
  return fetchJson<CoreListProjectsResponse>(`${getCoreBaseUrl()}/api/v1/projects`, {
    method: "GET",
  });
}

export async function coreGetProject(projectId: string): Promise<CoreProjectDetailDTO> {
  return fetchJson<CoreProjectDetailDTO>(`${getCoreBaseUrl()}/api/v1/projects/${projectId}`, {
    method: "GET",
  });
}

export async function coreCreateProject(
  payload: CoreCreateProjectPayload
): Promise<CoreCreateProjectResponse> {
  return fetchJson<CoreCreateProjectResponse>(`${getCoreBaseUrl()}/api/v1/projects`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function coreImportProject(folderPath: string): Promise<CoreCreateProjectResponse> {
  return fetchJson<CoreCreateProjectResponse>(`${getCoreBaseUrl()}/api/v1/projects/import`, {
    method: "POST",
    body: JSON.stringify({ folder_path: folderPath }),
  });
}

export async function coreUploadProject(files: File[]): Promise<CoreCreateProjectResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file, file.name);
  });
  return fetchFormData<CoreCreateProjectResponse>(`${getCoreBaseUrl()}/api/v1/projects/upload`, formData);
}

export async function coreImportAssets(projectId: string, folderPath: string): Promise<CoreAddAssetsResponse> {
  return fetchJson<CoreAddAssetsResponse>(`${getCoreBaseUrl()}/api/v1/projects/${projectId}/assets/import`, {
    method: "POST",
    body: JSON.stringify({ folder_path: folderPath }),
  });
}

export async function coreUploadAssets(projectId: string, files: File[]): Promise<CoreAddAssetsResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file, file.name);
  });
  return fetchFormData<CoreAddAssetsResponse>(
    `${getCoreBaseUrl()}/api/v1/projects/${projectId}/assets/upload`,
    formData
  );
}

export async function coreIngestProject(projectId: string): Promise<CoreIngestResponse> {
  return fetchJson<CoreIngestResponse>(`${getCoreBaseUrl()}/api/v1/ingest`, {
    method: "POST",
    body: JSON.stringify({ project_id: projectId }),
  });
}
