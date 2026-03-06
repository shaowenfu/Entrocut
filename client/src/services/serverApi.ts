import type { CoreClipDTO } from "./coreApi";
import { requestJson, type AppHttpError } from "./httpClient";
import type {
  AgentOperation,
  DecisionType,
  EntroVideoProject,
  PatchPayload,
} from "../contracts/contract";

export type { AppHttpError, DecisionType, AgentOperation };

export interface ChatDecisionResponse {
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

export interface ChatRequestPayload {
  project_id: string;
  message: string;
  session_id?: string;
  user_id?: string;
  context?: Record<string, unknown>;
  current_project?: Record<string, unknown>;
}

export interface IndexUpsertPayload {
  project_id: string;
  clips: CoreClipDTO[];
}

export interface IndexUpsertResponse {
  ok: boolean;
  request_id: string;
  indexed: number;
  failed: number;
}

export interface ServerJobAcceptedResponse {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  project_id: string;
  job_type: string;
  retryable: boolean;
}

export interface ServerJobStatusResponse {
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

const DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:8001";

function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function envBaseUrl(key: "VITE_SERVER_BASE_URL", fallback: string): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const value = env[key]?.trim();
  return trimTrailingSlash(value && value.length > 0 ? value : fallback);
}

export function getServerBaseUrl(): string {
  return envBaseUrl("VITE_SERVER_BASE_URL", DEFAULT_SERVER_BASE_URL);
}

export async function serverCreateIndexJob(payload: IndexUpsertPayload): Promise<ServerJobAcceptedResponse> {
  return requestJson<ServerJobAcceptedResponse>(`${getServerBaseUrl()}/api/v1/index/jobs`, {
    method: "POST",
    body: payload,
  });
}

export async function serverCreateChatJob(payload: ChatRequestPayload): Promise<ServerJobAcceptedResponse> {
  return requestJson<ServerJobAcceptedResponse>(`${getServerBaseUrl()}/api/v1/chat/jobs`, {
    method: "POST",
    body: payload,
  });
}

export async function serverGetJob(jobId: string): Promise<ServerJobStatusResponse> {
  return requestJson<ServerJobStatusResponse>(`${getServerBaseUrl()}/api/v1/jobs/${jobId}`, {
    method: "GET",
  });
}

export async function serverRetryJob(jobId: string): Promise<ServerJobAcceptedResponse> {
  return requestJson<ServerJobAcceptedResponse>(`${getServerBaseUrl()}/api/v1/jobs/${jobId}/retry`, {
    method: "POST",
  });
}

export async function serverUpsertClips(payload: IndexUpsertPayload): Promise<IndexUpsertResponse> {
  return requestJson<IndexUpsertResponse>(`${getServerBaseUrl()}/api/v1/index/upsert-clips`, {
    method: "POST",
    body: payload,
  });
}

export async function serverChat(payload: ChatRequestPayload): Promise<ChatDecisionResponse> {
  return requestJson<ChatDecisionResponse>(`${getServerBaseUrl()}/api/v1/chat`, {
    method: "POST",
    body: payload,
  });
}
