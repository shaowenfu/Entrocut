import { requestJson, type AppHttpError } from "./httpClient";

export type ProjectWorkflowState =
  | "prompt_input_required"
  | "awaiting_media"
  | "media_ready"
  | "media_processing"
  | "chat_thinking"
  | "ready"
  | "rendering"
  | "failed";

export type AssetType = "video" | "audio";
export type TaskType = "ingest" | "index" | "chat" | "render";
export type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface CoreProject {
  id: string;
  title: string;
  workflow_state: ProjectWorkflowState;
  created_at: string;
  updated_at: string;
}

export interface CoreAsset {
  id: string;
  name: string;
  duration_ms: number;
  type: AssetType;
  source_path?: string | null;
}

export interface CoreClip {
  id: string;
  asset_id: string;
  source_start_ms: number;
  source_end_ms: number;
  visual_desc: string;
  semantic_tags: string[];
  confidence?: number | null;
  thumbnail_ref?: string | null;
}

export interface CoreShot {
  id: string;
  clip_id: string;
  source_in_ms: number;
  source_out_ms: number;
  order: number;
  enabled: boolean;
  label?: string | null;
  intent?: string | null;
  note?: string | null;
  locked_fields?: Array<"source_range" | "order" | "clip_id" | "enabled">;
}

export interface CoreScene {
  id: string;
  shot_ids: string[];
  order: number;
  enabled: boolean;
  label?: string | null;
  intent?: string | null;
  note?: string | null;
  locked_fields?: Array<"shot_ids" | "order" | "enabled" | "intent">;
}

export interface CoreEditDraft {
  id: string;
  project_id: string;
  version: number;
  status: "draft" | "ready" | "rendering" | "failed";
  assets: CoreAsset[];
  clips: CoreClip[];
  shots: CoreShot[];
  scenes?: CoreScene[] | null;
  selected_scene_id?: string | null;
  selected_shot_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CoreChatUserTurn {
  id: string;
  role: "user";
  content: string;
}

export interface CoreAssistantDecisionOperation {
  id: string;
  action: string;
  target: string;
  summary: string;
}

export interface CoreChatAssistantTurn {
  id: string;
  role: "assistant";
  type: "decision";
  decision_type: string;
  reasoning_summary: string;
  ops: CoreAssistantDecisionOperation[];
}

export type CoreChatTurn = CoreChatUserTurn | CoreChatAssistantTurn;

export interface CoreTask {
  id: string;
  type: TaskType;
  status: TaskStatus;
  progress: number | null;
  message: string | null;
  created_at: string;
  updated_at: string;
}

export interface CoreWorkspaceSnapshot {
  project: CoreProject;
  edit_draft: CoreEditDraft;
  chat_turns: CoreChatTurn[];
  active_task: CoreTask | null;
}

export interface CoreExportResult {
  render_type: "export";
  output_url: string;
  duration_ms: number;
  file_size_bytes: number | null;
  thumbnail_url: string | null;
  format: string;
  quality: string | null;
  resolution: string | null;
}

export interface CoreEventEnvelope<T = unknown> {
  sequence: number;
  event: string;
  project_id: string;
  emitted_at: string;
  data: T;
}

export interface MediaFileReference {
  name: string;
  path?: string;
  size_bytes?: number;
  mime_type?: string;
}

export interface MediaReference {
  folder_path?: string;
  files?: MediaFileReference[];
}

export interface CreateProjectRequest {
  title?: string;
  prompt?: string;
  media?: MediaReference;
}

export interface CreateProjectResponse {
  project: CoreProject;
  workspace: CoreWorkspaceSnapshot;
}

export interface ListProjectsResponse {
  projects: CoreProject[];
}

export interface GetWorkspaceResponse {
  workspace: CoreWorkspaceSnapshot;
}

export interface TaskResponse {
  task: CoreTask;
}

export interface ImportAssetsRequest {
  media: MediaReference;
}

export interface ChatRequest {
  prompt: string;
  target?: {
    scene_id?: string | null;
    shot_id?: string | null;
  };
}

export interface ExportRequest {
  format?: string;
  quality?: string;
}

interface CoreAuthSessionRequest {
  access_token: string;
  user_id?: string | null;
}

interface CoreAuthSessionResponse {
  status: string;
  user_id?: string | null;
}

const DEFAULT_CORE_BASE_URL = "http://127.0.0.1:8000";

function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

export function getCoreBaseUrl(): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const fromEnv = env.VITE_CORE_BASE_URL?.trim();
  return trimTrailingSlash(fromEnv && fromEnv.length > 0 ? fromEnv : DEFAULT_CORE_BASE_URL);
}

function buildCoreUrl(path: string): string {
  return `${getCoreBaseUrl()}${path}`;
}

export function toMediaReference(input?: { folderPath?: string; files?: File[] } | null): MediaReference | undefined {
  if (!input) {
    return undefined;
  }
  const folderPath = input.folderPath?.trim();
  if (folderPath) {
    return { folder_path: folderPath };
  }
  const files = input.files
    ?.filter((file) => file.size > 0)
    .map((file) => {
      const maybePath = (file as File & { path?: string }).path;
      return {
        name: file.name,
        path: typeof maybePath === "string" && maybePath.trim().length > 0 ? maybePath : undefined,
        size_bytes: file.size,
        mime_type: file.type || undefined,
      };
    });
  if (files && files.length > 0) {
    return { files };
  }
  return undefined;
}

export async function listProjects(limit = 20): Promise<ListProjectsResponse> {
  return requestJson<ListProjectsResponse>(buildCoreUrl(`/api/v1/projects?limit=${limit}`), {
    method: "GET",
    authRequired: false,
  });
}

export async function createProject(payload: CreateProjectRequest): Promise<CreateProjectResponse> {
  return requestJson<CreateProjectResponse>(buildCoreUrl("/api/v1/projects"), {
    method: "POST",
    body: payload,
    authRequired: false,
  });
}

export async function getWorkspace(projectId: string): Promise<GetWorkspaceResponse> {
  return requestJson<GetWorkspaceResponse>(buildCoreUrl(`/api/v1/projects/${projectId}`), {
    method: "GET",
    authRequired: false,
  });
}

export async function importAssets(projectId: string, payload: ImportAssetsRequest): Promise<TaskResponse> {
  return requestJson<TaskResponse>(buildCoreUrl(`/api/v1/projects/${projectId}/assets:import`), {
    method: "POST",
    body: payload,
    authRequired: false,
  });
}

export async function sendChat(projectId: string, payload: ChatRequest): Promise<TaskResponse> {
  return requestJson<TaskResponse>(buildCoreUrl(`/api/v1/projects/${projectId}/chat`), {
    method: "POST",
    body: payload,
    authRequired: false,
  });
}

export async function syncCoreAuthSession(
  accessToken: string,
  userId?: string | null
): Promise<CoreAuthSessionResponse> {
  return requestJson<CoreAuthSessionResponse>(buildCoreUrl("/api/v1/auth/session"), {
    method: "POST",
    body: {
      access_token: accessToken,
      user_id: userId ?? undefined,
    } satisfies CoreAuthSessionRequest,
    authRequired: false,
  });
}

export async function clearCoreAuthSession(): Promise<CoreAuthSessionResponse> {
  return requestJson<CoreAuthSessionResponse>(buildCoreUrl("/api/v1/auth/session"), {
    method: "DELETE",
    authRequired: false,
  });
}

export async function exportProject(projectId: string, payload: ExportRequest = {}): Promise<TaskResponse> {
  return requestJson<TaskResponse>(buildCoreUrl(`/api/v1/projects/${projectId}/export`), {
    method: "POST",
    body: payload,
    authRequired: false,
  });
}

export function createProjectEventsSocket(projectId: string): WebSocket {
  const wsUrl = buildCoreUrl(`/api/v1/projects/${projectId}/events`).replace(/^http/, "ws");
  return new WebSocket(wsUrl);
}

export function toRequestError(error: unknown): AppHttpError {
  const maybe = error as AppHttpError;
  if (maybe && typeof maybe.code === "string" && typeof maybe.message === "string") {
    return maybe;
  }
  return {
    code: "CORE_REQUEST_FAILED",
    message: "core_request_failed",
    status: 0,
  };
}
