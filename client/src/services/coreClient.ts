import { requestJson, type AppHttpError } from "./httpClient";

export type ProjectSummaryState =
  | "blank"
  | "planning"
  | "media_processing"
  | "editing"
  | "exporting"
  | "attention_required";
export type ProjectLifecycleState = "active" | "archived";
export type AssetProcessingStage = "pending" | "segmenting" | "vectorizing" | "ready" | "failed";

export type AssetType = "video" | "audio";
export type TaskSlot = "media" | "agent" | "export";
export type TaskType = "ingest" | "index" | "chat" | "render";
export type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type ChatMode = "planning_only" | "editing";
export type ConversationFeedbackState = "unknown" | "clarify" | "approve" | "reject" | "revise";
export type ExecutionAgentRunState = "idle" | "planning" | "executing_tool" | "waiting_user" | "failed";

export interface CoreProject {
  id: string;
  title: string;
  summary_state?: ProjectSummaryState | null;
  lifecycle_state?: ProjectLifecycleState;
  created_at: string;
  updated_at: string;
}

export interface CoreAsset {
  id: string;
  name: string;
  duration_ms: number;
  type: AssetType;
  source_path?: string | null;
  processing_stage?: AssetProcessingStage;
  processing_progress?: number | null;
  clip_count?: number;
  indexed_clip_count?: number;
  last_error?: Record<string, unknown> | null;
  updated_at?: string | null;
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
  slot?: TaskSlot;
  type: TaskType;
  status: TaskStatus;
  owner_type?: "project" | "asset" | "draft";
  owner_id?: string | null;
  progress: number | null;
  message: string | null;
  result?: Record<string, unknown>;
  error?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface CoreProjectMediaSummary {
  asset_count: number;
  pending_asset_count: number;
  processing_asset_count: number;
  ready_asset_count: number;
  failed_asset_count: number;
  total_clip_count: number;
  indexed_clip_count: number;
  retrieval_ready: boolean;
}

export interface CoreProjectGoalState {
  brief?: string | null;
  constraints: string[];
  preferences: string[];
  open_questions: string[];
  updated_at?: string | null;
}

export interface CoreProjectFocusState {
  scope_type: "project" | "scene" | "shot";
  scene_id?: string | null;
  shot_id?: string | null;
  updated_at?: string | null;
}

export interface CoreProjectConversationState {
  pending_questions: string[];
  confirmed_facts: string[];
  latest_user_feedback: ConversationFeedbackState;
  updated_at?: string | null;
}

export interface CoreProjectRetrievalState {
  last_query?: string | null;
  candidate_clip_ids: string[];
  retrieval_ready: boolean;
  blocking_reason?: string | null;
  updated_at?: string | null;
}

export interface CoreProjectExecutionState {
  agent_run_state: ExecutionAgentRunState;
  current_task_id?: string | null;
  last_tool_name?: string | null;
  last_error?: Record<string, unknown> | null;
  updated_at?: string | null;
}

export interface CoreProjectRuntimeState {
  goal_state: CoreProjectGoalState;
  focus_state: CoreProjectFocusState;
  conversation_state: CoreProjectConversationState;
  retrieval_state: CoreProjectRetrievalState;
  execution_state: CoreProjectExecutionState;
  updated_at?: string | null;
}

export interface CoreProjectCapabilities {
  can_send_chat: boolean;
  chat_mode: ChatMode;
  can_retrieve: boolean;
  can_inspect: boolean;
  can_patch_draft: boolean;
  can_preview: boolean;
  can_export: boolean;
  blocking_reasons: string[];
}

export interface CoreWorkspaceSnapshot {
  project: CoreProject;
  edit_draft: CoreEditDraft;
  chat_turns: CoreChatTurn[];
  summary_state?: ProjectSummaryState | null;
  media_summary: CoreProjectMediaSummary;
  runtime_state: CoreProjectRuntimeState;
  capabilities: CoreProjectCapabilities;
  active_tasks: CoreTask[];
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

type DesktopMediaLike = {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
};

function isDesktopMediaLike(file: File | DesktopMediaLike): file is DesktopMediaLike {
  return "path" in file && typeof file.path === "string";
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
  model?: string;
  target?: {
    scene_id?: string | null;
    shot_id?: string | null;
  };
}

export interface ChatRoutingOptions {
  mode: "Platform" | "BYOK";
  byokKey?: string;
  byokBaseUrl?: string;
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

export function toMediaReference(
  input?: { folderPath?: string; files?: Array<File | DesktopMediaLike> } | null
): MediaReference | undefined {
  if (!input) {
    return undefined;
  }
  const files = input.files
    ?.filter((file) => {
      if (isDesktopMediaLike(file)) {
        return file.path.trim().length > 0;
      }
      return file.size > 0;
    })
    .map((file) => {
      if (isDesktopMediaLike(file)) {
        return {
          name: file.name,
          path: file.path,
          size_bytes: file.size_bytes,
          mime_type: file.mime_type,
        };
      }
      const maybePath = (file as File & { path?: string }).path;
      return {
        name: file.name,
        path: typeof maybePath === "string" && maybePath.trim().length > 0 ? maybePath : undefined,
        size_bytes: (file as File).size,
        mime_type: (file as File).type || undefined,
      };
    });
  if (files && files.length > 0) {
    return { files };
  }
  const folderPath = input.folderPath?.trim();
  if (folderPath) {
    return { folder_path: folderPath };
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

export async function sendChat(
  projectId: string,
  payload: ChatRequest,
  routing: ChatRoutingOptions
): Promise<TaskResponse> {
  const headers: Record<string, string> = {
    "X-Routing-Mode": routing.mode,
  };
  if (routing.mode === "BYOK" && routing.byokKey) {
    headers["X-BYOK-Key"] = routing.byokKey;
  }
  if (routing.mode === "BYOK" && routing.byokBaseUrl) {
    headers["X-BYOK-BaseURL"] = routing.byokBaseUrl;
  }
  return requestJson<TaskResponse>(buildCoreUrl(`/api/v1/projects/${projectId}/chat`), {
    method: "POST",
    body: payload,
    headers,
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
