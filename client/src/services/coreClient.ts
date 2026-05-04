import { requestJson, type AppHttpError } from "./httpClient";

// 项目摘要状态，用于 Launchpad/Workspace 展示当前阶段。
export type ProjectSummaryState =
  | "blank"
  | "planning"
  | "media_processing"
  | "editing"
  | "exporting"
  | "attention_required";
// 项目生命周期状态。
export type ProjectLifecycleState = "active" | "archived";
// 媒体资产处理阶段。
export type AssetProcessingStage = "pending" | "segmenting" | "vectorizing" | "ready" | "failed";

// core 支持的媒体资产类型。
export type AssetType = "video" | "audio";
// 后台任务占用的能力槽位。
export type TaskSlot = "media" | "agent" | "preview" | "export";
// 后台任务类型。
export type TaskType = "ingest" | "index" | "chat" | "render";
// 后台任务状态。
export type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
// 聊天模式：仅规划或可编辑。
export type ChatMode = "planning_only" | "editing";
// 用户反馈分类。
export type ConversationFeedbackState = "unknown" | "clarify" | "approve" | "reject" | "revise";
// Agent 执行状态。
export type ExecutionAgentRunState = "idle" | "planning" | "executing_tool" | "waiting_user" | "failed";

// core 项目摘要。
export interface CoreProject {
  id: string;
  title: string;
  summary_state?: ProjectSummaryState | null;
  lifecycle_state?: ProjectLifecycleState;
  created_at: string;
  updated_at: string;
}

// core 媒体资产。
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

// core 检索/切分后的素材片段。
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

// EditDraft 中的单个 shot。
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

// EditDraft 中的场景。
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

// core 编辑草稿，是 Workspace 的主要事实源。
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

// 用户聊天轮次。
export interface CoreChatUserTurn {
  id: string;
  role: "user";
  content: string;
}

// Assistant 决策中的单个操作摘要。
export interface CoreAssistantDecisionOperation {
  id: string;
  action: string;
  target: string;
  summary: string;
}

// Assistant 决策轮次。
export interface CoreChatAssistantTurn {
  id: string;
  role: "assistant";
  type: "decision";
  decision_type: string;
  reasoning_summary: string;
  ops: CoreAssistantDecisionOperation[];
}

// 聊天轮次联合类型。
export type CoreChatTurn = CoreChatUserTurn | CoreChatAssistantTurn;

// core 后台任务。
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

// 项目媒体处理统计。
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

// 项目目标状态。
export interface CoreProjectGoalState {
  brief?: string | null;
  constraints: string[];
  preferences: string[];
  open_questions: string[];
  updated_at?: string | null;
}

// 当前操作焦点。
export interface CoreProjectFocusState {
  scope_type: "project" | "scene" | "shot";
  scene_id?: string | null;
  shot_id?: string | null;
  updated_at?: string | null;
}

// 项目对话状态。
export interface CoreProjectConversationState {
  pending_questions: string[];
  confirmed_facts: string[];
  latest_user_feedback: ConversationFeedbackState;
  updated_at?: string | null;
}

// 项目检索状态。
export interface CoreProjectRetrievalState {
  last_query?: string | null;
  candidate_clip_ids: string[];
  candidate_scores?: Record<string, number>;
  selected_candidate_id?: string | null;
  inspection_summary?: string | null;
  retrieval_ready: boolean;
  blocking_reason?: string | null;
  updated_at?: string | null;
}

// 项目执行状态。
export interface CoreProjectExecutionState {
  agent_run_state: ExecutionAgentRunState;
  current_task_id?: string | null;
  last_tool_name?: string | null;
  last_error?: Record<string, unknown> | null;
  updated_at?: string | null;
}

// Workspace 运行态聚合。
export interface CoreProjectRuntimeState {
  goal_state: CoreProjectGoalState;
  focus_state: CoreProjectFocusState;
  conversation_state: CoreProjectConversationState;
  retrieval_state: CoreProjectRetrievalState;
  execution_state: CoreProjectExecutionState;
  updated_at?: string | null;
}

// core 当前允许的能力集合。
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

// Workspace 首屏/刷新快照。
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
  preview_result?: Record<string, unknown> | null;
  export_result?: Record<string, unknown> | null;
}

// Agent 步骤事件项。
export interface CoreAgentStepItem {
  phase: string;
  summary: string;
  details: Record<string, unknown>;
  status?: string;
  iteration?: number;
  emitted_at?: string;
}

// 导出结果。
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

// core WebSocket 事件信封。
export interface CoreEventEnvelope<T = unknown> {
  sequence: number;
  event: string;
  project_id: string;
  emitted_at: string;
  data: T;
}

// 传给 core 的媒体文件引用。
export interface MediaFileReference {
  name: string;
  path?: string;
  size_bytes?: number;
  mime_type?: string;
}

// 传给 core 的媒体引用：目录或文件列表。
export interface MediaReference {
  folder_path?: string;
  files?: MediaFileReference[];
}

// Electron bridge 传来的桌面媒体引用形状。
type DesktopMediaLike = {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
};

// 判断媒体文件是否带可信本地路径。
function isDesktopMediaLike(file: File | DesktopMediaLike): file is DesktopMediaLike {
  return "path" in file && typeof file.path === "string";
}

// 把 Windows WSL UNC 路径转换成本地 Linux 路径。
function normalizePathForLocalCore(nativePath: string): string {
  const wslMatch = nativePath.match(/^\\\\wsl(?:\.localhost|\$)\\[^\\]+\\(.+)$/i);
  if (!wslMatch) {
    return nativePath;
  }
  return `/${wslMatch[1]!.replaceAll("\\", "/")}`;
}

// 创建项目请求。
export interface CreateProjectRequest {
  title?: string;
  prompt?: string;
  media?: MediaReference;
}

// 创建项目响应。
export interface CreateProjectResponse {
  project: CoreProject;
  workspace: CoreWorkspaceSnapshot;
}

// 项目列表响应。
export interface ListProjectsResponse {
  projects: CoreProject[];
}

// Workspace 快照响应。
export interface GetWorkspaceResponse {
  workspace: CoreWorkspaceSnapshot;
}

// 启动后台任务后的响应。
export interface TaskResponse {
  task: CoreTask;
}

// 导入资产请求。
export interface ImportAssetsRequest {
  media: MediaReference;
}

// 发送聊天请求。
export interface ChatRequest {
  prompt: string;
  model?: string;
  target?: {
    scene_id?: string | null;
    shot_id?: string | null;
  };
}

// 聊天路由参数：平台模型或 BYOK。
export interface ChatRoutingOptions {
  mode: "Platform" | "BYOK";
  byokKey?: string;
  byokBaseUrl?: string;
}

// 导出请求参数。
export interface ExportRequest {
  format?: string;
  quality?: string;
}

// 同步登录态给 core 的请求。
interface CoreAuthSessionRequest {
  access_token: string;
  user_id?: string | null;
}

// core 登录态同步响应。
interface CoreAuthSessionResponse {
  status: string;
  user_id?: string | null;
}

// 默认 core API 地址。
const DEFAULT_CORE_BASE_URL = "http://127.0.0.1:8000";

// Electron main 启动 core 后动态写入的 base URL。
let runtimeCoreBaseUrl: string | null = null;

// 去掉 URL 末尾斜杠，避免拼接路径时出现双斜杠。
function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

// 设置运行时 core base URL。
export function setRuntimeCoreBaseUrl(baseUrl: string | null): void {
  runtimeCoreBaseUrl = baseUrl ? trimTrailingSlash(baseUrl) : null;
}

// 获取 core base URL，优先运行时地址，其次环境变量，最后默认本地地址。
export function getCoreBaseUrl(): string {
  if (runtimeCoreBaseUrl) {
    return runtimeCoreBaseUrl;
  }
  const env = import.meta.env as Record<string, string | undefined>;
  const fromEnv = env.VITE_CORE_BASE_URL?.trim();
  return trimTrailingSlash(fromEnv && fromEnv.length > 0 ? fromEnv : DEFAULT_CORE_BASE_URL);
}

// 拼接 core API URL。
function buildCoreUrl(path: string): string {
  return `${getCoreBaseUrl()}${path}`;
}

// 把 Renderer 媒体选择结果转换成 core 接口需要的 MediaReference。
export function toMediaReference(
  input?: { folderPath?: string; files?: Array<File | DesktopMediaLike> } | null
): MediaReference | undefined {
  if (!input) {
    return undefined;
  }
  const files: MediaFileReference[] = [];
  for (const file of input.files ?? []) {
    if (isDesktopMediaLike(file)) {
      const normalizedPath = normalizePathForLocalCore(file.path.trim());
      if (normalizedPath.length === 0) {
        continue;
      }
      files.push({
        name: file.name,
        path: normalizedPath,
        size_bytes: file.size_bytes,
        mime_type: file.mime_type,
      });
      continue;
    }
    if (file.size <= 0) {
      continue;
    }
    const maybePath = (file as File & { path?: string }).path;
    if (typeof maybePath !== "string" || maybePath.trim().length === 0) {
      continue;
    }
    files.push({
      name: file.name,
      path: normalizePathForLocalCore(maybePath.trim()),
      size_bytes: file.size,
      mime_type: file.type || undefined,
    });
  }
  if (files.length > 0) {
    return { files };
  }
  const folderPath = input.folderPath?.trim();
  if (folderPath) {
    return { folder_path: folderPath };
  }
  return undefined;
}

// 获取项目列表。
export async function listProjects(limit = 20): Promise<ListProjectsResponse> {
  return requestJson<ListProjectsResponse>(buildCoreUrl(`/api/v1/projects?limit=${limit}`), {
    method: "GET",
    authRequired: false,
  });
}

// 创建项目。
export async function createProject(payload: CreateProjectRequest): Promise<CreateProjectResponse> {
  return requestJson<CreateProjectResponse>(buildCoreUrl("/api/v1/projects"), {
    method: "POST",
    body: payload,
    authRequired: false,
  });
}

// 拉取单个 Workspace 快照。
export async function getWorkspace(projectId: string): Promise<GetWorkspaceResponse> {
  return requestJson<GetWorkspaceResponse>(buildCoreUrl(`/api/v1/projects/${projectId}`), {
    method: "GET",
    authRequired: false,
  });
}

// 向项目导入媒体资产。
export async function importAssets(projectId: string, payload: ImportAssetsRequest): Promise<TaskResponse> {
  return requestJson<TaskResponse>(buildCoreUrl(`/api/v1/projects/${projectId}/assets:import`), {
    method: "POST",
    body: payload,
    authRequired: false,
  });
}

// 发送用户 chat 给 core，并传入模型路由信息。
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

// 把 server 登录态同步到本地 core。
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

// 清除本地 core 登录态。
export async function clearCoreAuthSession(): Promise<CoreAuthSessionResponse> {
  return requestJson<CoreAuthSessionResponse>(buildCoreUrl("/api/v1/auth/session"), {
    method: "DELETE",
    authRequired: false,
  });
}

// 请求导出项目。
export async function exportProject(projectId: string, payload: ExportRequest = {}): Promise<TaskResponse> {
  return requestJson<TaskResponse>(buildCoreUrl(`/api/v1/projects/${projectId}/export`), {
    method: "POST",
    body: payload,
    authRequired: false,
  });
}

// 创建项目事件 WebSocket 连接。
export function createProjectEventsSocket(projectId: string): WebSocket {
  const wsUrl = buildCoreUrl(`/api/v1/projects/${projectId}/events`).replace(/^http/, "ws");
  return new WebSocket(wsUrl);
}

// 把未知错误归一化成 AppHttpError。
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
