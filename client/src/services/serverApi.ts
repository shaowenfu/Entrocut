import type { CoreClipDTO } from "./coreApi";

export type DecisionType =
  | "UPDATE_PROJECT_CONTRACT"
  | "APPLY_PATCH_ONLY"
  | "ASK_USER_CLARIFICATION";

export interface ChatDecisionResponse {
  decision_type: DecisionType;
  project_id: string;
  reasoning_summary: string;
  ops: string[];
  storyboard_scenes?: Array<{
    id: string;
    title: string;
    duration: string;
    intent: string;
  }>;
  meta?: {
    request_id?: string;
    latency_ms?: number;
  };
}

export interface ChatRequestPayload {
  project_id: string;
  message: string;
  session_id?: string;
  user_id?: string;
  context?: Record<string, unknown>;
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

export interface AppHttpError {
  code: "HTTP_ERROR" | "NETWORK_ERROR";
  message: string;
  cause?: string;
}

const REQUEST_TIMEOUT_MS = 8000;
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

function toHttpError(code: AppHttpError["code"], message: string, cause?: unknown): AppHttpError {
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

export async function serverUpsertClips(payload: IndexUpsertPayload): Promise<IndexUpsertResponse> {
  return fetchJson<IndexUpsertResponse>(`${getServerBaseUrl()}/api/v1/index/upsert-clips`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function serverChat(payload: ChatRequestPayload): Promise<ChatDecisionResponse> {
  return fetchJson<ChatDecisionResponse>(`${getServerBaseUrl()}/api/v1/chat`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
