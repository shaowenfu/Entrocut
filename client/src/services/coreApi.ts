import { requestJson, type AppHttpError } from "./httpClient";
import type {
  AgentOperation,
  DecisionType,
  EntroVideoProject,
  PatchPayload,
} from "../contracts/contract";

export type { AppHttpError };

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
  contract_version: string;
  project_id: string;
  title: string;
  ai_status: string;
  last_ai_edit: string;
  assets: CoreAssetDTO[];
  clips: CoreClipDTO[];
}

export interface CoreIngestResponse {
  contract_version: string;
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
  contract_version: string;
  project_id: string;
  title: string;
}

export interface CoreListProjectsResponse {
  items: CoreProjectMetaDTO[];
}

interface CoreAddAssetsResponse {
  contract_version: string;
  project_id: string;
  added_count: number;
  total_assets: number;
}

export interface CoreJobAcceptedResponse {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  project_id: string;
  job_type: string;
  retryable: boolean;
}

export interface CoreJobStatusResponse {
  job_id: string;
  project_id: string;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  retryable: boolean;
  error_code?: string | null;
  error_message?: string | null;
  result?: Record<string, unknown> | null;
  updated_at: string;
}

export interface CoreIndexUpsertPayload {
  project_id: string;
  clips: CoreClipDTO[];
}

export interface CoreIndexUpsertResponse {
  ok: boolean;
  request_id: string;
  indexed: number;
  failed: number;
}

export interface CoreChatRequestPayload {
  project_id: string;
  message: string;
  session_id?: string;
  user_id?: string;
  context?: Record<string, unknown>;
  current_project?: Record<string, unknown>;
}

export interface CoreChatDecisionResponse {
  decision_type: DecisionType;
  project: EntroVideoProject | null;
  patch: PatchPayload | null;
  project_id: string;
  reasoning_summary: string;
  ops: AgentOperation[];
  storyboard_scenes?: Array<{
    id: string;
    title: string;
    duration: string;
    intent: string;
  }>;
  meta?: {
    request_id?: string;
    latency_ms?: number;
    session_id?: string;
    used_clip_count?: number;
  };
}

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

export async function coreListProjects(): Promise<CoreListProjectsResponse> {
  return requestJson<CoreListProjectsResponse>(`${getCoreBaseUrl()}/api/v1/projects`, {
    method: "GET",
  });
}

export async function coreGetProject(projectId: string): Promise<CoreProjectDetailDTO> {
  return requestJson<CoreProjectDetailDTO>(`${getCoreBaseUrl()}/api/v1/projects/${projectId}`, {
    method: "GET",
  });
}

export async function coreCreateProject(
  payload: CoreCreateProjectPayload
): Promise<CoreCreateProjectResponse> {
  return requestJson<CoreCreateProjectResponse>(`${getCoreBaseUrl()}/api/v1/projects`, {
    method: "POST",
    body: payload,
  });
}

export async function coreImportProject(folderPath: string): Promise<CoreCreateProjectResponse> {
  return requestJson<CoreCreateProjectResponse>(`${getCoreBaseUrl()}/api/v1/projects/import`, {
    method: "POST",
    body: { folder_path: folderPath },
  });
}

export async function coreUploadProject(files: File[]): Promise<CoreCreateProjectResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file, file.name);
  });
  return requestJson<CoreCreateProjectResponse>(`${getCoreBaseUrl()}/api/v1/projects/upload`, {
    method: "POST",
    body: formData,
  });
}

export async function coreImportAssets(
  projectId: string,
  folderPath: string
): Promise<CoreAddAssetsResponse> {
  return requestJson<CoreAddAssetsResponse>(
    `${getCoreBaseUrl()}/api/v1/projects/${projectId}/assets/import`,
    {
      method: "POST",
      body: { folder_path: folderPath },
    }
  );
}

export async function coreUploadAssets(
  projectId: string,
  files: File[]
): Promise<CoreAddAssetsResponse> {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file, file.name);
  });
  return requestJson<CoreAddAssetsResponse>(
    `${getCoreBaseUrl()}/api/v1/projects/${projectId}/assets/upload`,
    {
      method: "POST",
      body: formData,
    }
  );
}

export async function coreCreateIngestJob(projectId: string): Promise<CoreJobAcceptedResponse> {
  return requestJson<CoreJobAcceptedResponse>(`${getCoreBaseUrl()}/api/v1/ingest/jobs`, {
    method: "POST",
    body: { project_id: projectId },
  });
}

export async function coreGetJob(jobId: string): Promise<CoreJobStatusResponse> {
  return requestJson<CoreJobStatusResponse>(`${getCoreBaseUrl()}/api/v1/jobs/${jobId}`, {
    method: "GET",
  });
}

export async function coreRetryJob(jobId: string): Promise<CoreJobAcceptedResponse> {
  return requestJson<CoreJobAcceptedResponse>(`${getCoreBaseUrl()}/api/v1/jobs/${jobId}/retry`, {
    method: "POST",
  });
}

export async function coreIngestProject(projectId: string): Promise<CoreIngestResponse> {
  return requestJson<CoreIngestResponse>(`${getCoreBaseUrl()}/api/v1/ingest`, {
    method: "POST",
    body: { project_id: projectId },
  });
}

export async function coreUpsertClips(
  payload: CoreIndexUpsertPayload
): Promise<CoreIndexUpsertResponse> {
  return requestJson<CoreIndexUpsertResponse>(`${getCoreBaseUrl()}/api/v1/index/upsert-clips`, {
    method: "POST",
    body: payload,
  });
}

export async function coreChat(payload: CoreChatRequestPayload): Promise<CoreChatDecisionResponse> {
  return requestJson<CoreChatDecisionResponse>(`${getCoreBaseUrl()}/api/v1/chat`, {
    method: "POST",
    body: payload,
  });
}
