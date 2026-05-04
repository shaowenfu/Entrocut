import { isElectronEnvironment } from "./electronBridge";
import { clearCoreAuthSession, syncCoreAuthSession } from "./coreClient";
import { getAuthToken, persistAuthToken, requestJson } from "./httpClient";

// 远程 server API 地址，用于登录、用户信息和 token 刷新。
const SERVER_BASE_URL = (
  (import.meta.env as Record<string, string | undefined>).VITE_SERVER_BASE_URL?.trim() ||
  "http://127.0.0.1:8001"
).replace(/\/$/, "");
// 开发态登录模式；Electron 可用 polling 模式模拟网页登录回跳。
const AUTH_LOGIN_MODE = (import.meta.env as Record<string, string | undefined>).VITE_AUTH_LOGIN_MODE?.trim();

// 旧版 refresh token 的 localStorage key。
const REFRESH_STORAGE_KEY = "ENTROCUT_REFRESH_TOKEN";
// 桌面端安全存储中的 refresh token key。
const SECURE_REFRESH_STORAGE_KEY = "entrocut.auth.refresh_token";
// 标记 Electron polling 登录页，避免 Web 页面误处理回跳。
const ELECTRON_POLLING_REDIRECT_MARKER = "electron_polling";
// 登录 session 轮询间隔。
const LOGIN_POLL_INTERVAL_MS = 1_000;
// 登录 session 最大等待时间。
const LOGIN_POLL_TIMEOUT_MS = 120_000;

// 内存中的 refresh token 缓存。
let cachedRefreshToken: string | null = null;
// 防止重复初始化 refresh token 存储。
let refreshStorageInitialized = false;

// 登录用户信息。
export interface AuthUser {
  id: string;
  email?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  status: string;
  credits_balance: number;
}

// 创建第三方登录 session 的响应。
interface LoginSessionCreateResponse {
  login_session_id: string;
  authorize_url: string;
  expires_in: number;
}

// 查询/认领第三方登录 session 的响应。
interface LoginSessionClaimResponse {
  login_session_id: string;
  provider: string;
  status: "pending" | "authenticated" | "consumed" | "failed" | "expired";
  result: {
    access_token: string;
    refresh_token: string;
    expires_in: number;
    token_type: string;
    user: AuthUser;
  } | null;
  error: {
    code?: string;
    message?: string;
  } | null;
}

// 当前用户接口响应。
interface MeResponse {
  user: AuthUser;
}

// refresh token 换取 access token 的响应。
interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

// 拼接 server API URL。
function endpoint(path: string): string {
  return `${SERVER_BASE_URL}${path}`;
}

// 简单异步等待，用于登录轮询。
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

// 开发态 Electron polling 登录是否启用。
export function isDevLoginPollingEnabled(): boolean {
  return Boolean(import.meta.env.DEV && AUTH_LOGIN_MODE === "polling" && isElectronEnvironment());
}

// 计算登录完成后的客户端回跳地址。
function getClientRedirectUri(): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  if (isDevLoginPollingEnabled()) {
    const url = new URL(window.location.origin);
    url.searchParams.set("auth_client", ELECTRON_POLLING_REDIRECT_MARKER);
    return url.toString();
  }
  return isElectronEnvironment() ? undefined : `${window.location.origin}/`;
}

// 把当前 Web 登录态同步给本地 core。
export async function syncCoreAuthSessionState(userId?: string | null): Promise<void> {
  const token = getAuthToken();
  if (!token) {
    await clearCoreAuthSession();
    return;
  }
  await syncCoreAuthSession(token, userId);
}

// 清除本地 core 中的登录态。
export async function clearCoreAuthSessionState(): Promise<void> {
  await clearCoreAuthSession();
}

// 读取 refresh token，优先内存缓存，其次旧 localStorage。
export function getRefreshToken(): string | null {
  if (cachedRefreshToken && cachedRefreshToken.trim()) {
    return cachedRefreshToken.trim();
  }
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(REFRESH_STORAGE_KEY)?.trim() || null;
}

// 更新内存 refresh token；持久化交给 persistRefreshToken。
export function setRefreshToken(token: string | null): void {
  const normalized = token?.trim() || null;
  cachedRefreshToken = normalized;
  if (typeof window === "undefined") {
    return;
  }
}

// 初始化 refresh token 存储，并迁移旧 localStorage token 到 Electron secure store。
export async function initializeRefreshTokenStorage(): Promise<void> {
  if (refreshStorageInitialized) {
    return;
  }
  refreshStorageInitialized = true;
  if (typeof window === "undefined") {
    return;
  }

  const electron = window.electron;
  const legacyToken = window.localStorage.getItem(REFRESH_STORAGE_KEY)?.trim() || null;
  if (electron?.getSecureCredential) {
    const secureToken = (await electron.getSecureCredential(SECURE_REFRESH_STORAGE_KEY))?.trim() || null;
    if (secureToken) {
      cachedRefreshToken = secureToken;
      if (legacyToken) {
        window.localStorage.removeItem(REFRESH_STORAGE_KEY);
      }
      return;
    }
    if (legacyToken) {
      cachedRefreshToken = legacyToken;
      await electron.setSecureCredential?.(SECURE_REFRESH_STORAGE_KEY, legacyToken);
      window.localStorage.removeItem(REFRESH_STORAGE_KEY);
      return;
    }
    cachedRefreshToken = null;
    return;
  }

  cachedRefreshToken = legacyToken;
}

// 持久化 refresh token：桌面端写 secure store，Web fallback 写 localStorage。
export async function persistRefreshToken(token: string | null): Promise<void> {
  const normalized = token?.trim() || null;
  cachedRefreshToken = normalized;
  if (typeof window === "undefined") {
    return;
  }

  const electron = window.electron;
  if (electron?.setSecureCredential) {
    if (!normalized) {
      await electron.deleteSecureCredential?.(SECURE_REFRESH_STORAGE_KEY);
    } else {
      await electron.setSecureCredential(SECURE_REFRESH_STORAGE_KEY, normalized);
    }
    window.localStorage.removeItem(REFRESH_STORAGE_KEY);
    return;
  }

  if (!normalized) {
    window.localStorage.removeItem(REFRESH_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(REFRESH_STORAGE_KEY, normalized);
}

// 创建 Google 登录 session。
export async function createGoogleLoginSession(): Promise<LoginSessionCreateResponse> {
  const clientRedirectUri = getClientRedirectUri();
  return requestJson<LoginSessionCreateResponse>(endpoint("/api/v1/auth/login-sessions"), {
    method: "POST",
    authRequired: false,
    body: {
      provider: "google",
      client_redirect_uri: clientRedirectUri,
    },
  });
}

// 创建 GitHub 登录 session。
export async function createGithubLoginSession(): Promise<LoginSessionCreateResponse> {
  const clientRedirectUri = getClientRedirectUri();
  return requestJson<LoginSessionCreateResponse>(endpoint("/api/v1/auth/login-sessions"), {
    method: "POST",
    authRequired: false,
    body: {
      provider: "github",
      client_redirect_uri: clientRedirectUri,
    },
  });
}

// 查询登录 session 当前状态。
export async function fetchLoginSession(loginSessionId: string): Promise<LoginSessionClaimResponse> {
  return requestJson<LoginSessionClaimResponse>(
    endpoint(`/api/v1/auth/login-sessions/${encodeURIComponent(loginSessionId)}`),
    {
      authRequired: false,
    }
  );
}

// 持久化登录 session 结果，并同步给 core。
async function persistLoginSessionResult(response: LoginSessionClaimResponse): Promise<AuthUser> {
  if (!response.result?.access_token || !response.result.refresh_token) {
    throw {
      code: response.error?.code ?? "AUTH_LOGIN_SESSION_UNAVAILABLE",
      message: response.error?.message ?? "login_session_result_unavailable",
      status: 400,
    };
  }
  await persistAuthToken(response.result.access_token);
  await persistRefreshToken(response.result.refresh_token);
  await syncCoreAuthSession(response.result.access_token, response.result.user.id);
  return response.result.user;
}

// 认领已完成的登录 session。
export async function claimLoginSession(loginSessionId: string): Promise<AuthUser> {
  const response = await fetchLoginSession(loginSessionId);
  return persistLoginSessionResult(response);
}

// 轮询等待登录 session 完成，适用于 Electron 开发态 polling 登录。
export async function waitForLoginSession(loginSessionId: string): Promise<AuthUser> {
  const deadline = Date.now() + LOGIN_POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const response = await fetchLoginSession(loginSessionId);
    if (response.result?.access_token && response.result.refresh_token) {
      return persistLoginSessionResult(response);
    }
    if (response.status === "failed" || response.status === "expired" || response.status === "consumed") {
      throw {
        code: response.error?.code ?? `AUTH_LOGIN_SESSION_${response.status.toUpperCase()}`,
        message: response.error?.message ?? `login_session_${response.status}`,
        status: 400,
      };
    }
    await delay(LOGIN_POLL_INTERVAL_MS);
  }
  throw {
    code: "AUTH_LOGIN_SESSION_TIMEOUT",
    message: "login_session_timeout",
    status: 408,
  };
}

// 拉取当前登录用户。
export async function fetchCurrentUser(): Promise<AuthUser> {
  const response = await requestJson<MeResponse>(endpoint("/api/v1/me"));
  return response.user;
}

// 使用 refresh token 刷新 access token，并同步给 core。
export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }
  const response = await requestJson<RefreshResponse>(endpoint("/api/v1/auth/refresh"), {
    method: "POST",
    authRequired: false,
    body: {
      refresh_token: refreshToken,
    },
  });
  await persistAuthToken(response.access_token);
  await persistRefreshToken(response.refresh_token);
  await syncCoreAuthSession(response.access_token);
  return response.access_token;
}

// 登出当前用户，并清理 Web 和 core 登录态。
export async function logoutCurrentUser(): Promise<void> {
  try {
    await requestJson(endpoint("/api/v1/auth/logout"), {
      method: "POST",
    });
  } finally {
    await persistAuthToken("");
    await persistRefreshToken(null);
    await clearCoreAuthSession();
  }
}
