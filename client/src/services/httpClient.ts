// 后端统一错误响应结构。
export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// 前端内部统一使用的 HTTP 错误对象。
export interface AppHttpError {
  code: string;
  message: string;
  status: number;
  requestId?: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

// 默认请求超时时间。
const DEFAULT_TIMEOUT_MS = 10000;
// 旧版 access token 的 localStorage key。
const AUTH_STORAGE_KEY = "ENTROCUT_AUTH_TOKEN";
// 桌面端安全存储中的 access token key。
const SECURE_AUTH_STORAGE_KEY = "entrocut.auth.access_token";

// 内存中的 access token 缓存。
let cachedAuthToken: string | null = null;
// 防止重复初始化 token 存储。
let authStorageInitialized = false;

// 生成请求追踪 id，用于前后端日志串联。
function randomRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `req_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  }
  const suffix = Math.random().toString(16).slice(2, 14);
  return `req_${suffix}`;
}

// 保持错误对象类型稳定，后续可集中扩展错误规范化。
function toHttpError(error: AppHttpError): AppHttpError {
  return error;
}

// 读取当前 access token，优先级：环境变量 > 内存缓存 > localStorage。
export function getAuthToken(): string | null {
  const env = import.meta.env as Record<string, string | undefined>;
  const envToken = env.VITE_AUTH_TOKEN?.trim();
  if (envToken) {
    return envToken;
  }
  if (cachedAuthToken && cachedAuthToken.trim()) {
    return cachedAuthToken.trim();
  }
  if (typeof window === "undefined") {
    return null;
  }
  const saved = window.localStorage.getItem(AUTH_STORAGE_KEY);
  return saved?.trim() || null;
}

// 更新内存 access token；浏览器持久化交给 persistAuthToken。
export function setAuthToken(token: string): void {
  const normalized = token.trim();
  cachedAuthToken = normalized || null;
  if (typeof window === "undefined") {
    return;
  }
  if (!normalized) {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    return;
  }
}

// 初始化 access token 存储，并把旧 localStorage token 迁移到 Electron secure store。
export async function initializeAuthTokenStorage(): Promise<void> {
  if (authStorageInitialized) {
    return;
  }
  authStorageInitialized = true;

  const env = import.meta.env as Record<string, string | undefined>;
  const envToken = env.VITE_AUTH_TOKEN?.trim();
  if (envToken) {
    cachedAuthToken = envToken;
    return;
  }
  if (typeof window === "undefined") {
    return;
  }

  const electron = window.electron;
  const legacyToken = window.localStorage.getItem(AUTH_STORAGE_KEY)?.trim() || null;
  if (electron?.getSecureCredential) {
    const secureToken = (await electron.getSecureCredential(SECURE_AUTH_STORAGE_KEY))?.trim() || null;
    if (secureToken) {
      cachedAuthToken = secureToken;
      if (legacyToken) {
        window.localStorage.removeItem(AUTH_STORAGE_KEY);
      }
      return;
    }
    if (legacyToken) {
      cachedAuthToken = legacyToken;
      await electron.setSecureCredential?.(SECURE_AUTH_STORAGE_KEY, legacyToken);
      window.localStorage.removeItem(AUTH_STORAGE_KEY);
      return;
    }
    cachedAuthToken = null;
    return;
  }

  cachedAuthToken = legacyToken;
}

// 持久化 access token：桌面端写 secure store，Web fallback 写 localStorage。
export async function persistAuthToken(token: string): Promise<void> {
  const normalized = token.trim();
  cachedAuthToken = normalized || null;
  if (typeof window === "undefined") {
    return;
  }
  const electron = window.electron;
  if (electron?.setSecureCredential) {
    if (!normalized) {
      await electron.deleteSecureCredential?.(SECURE_AUTH_STORAGE_KEY);
    } else {
      await electron.setSecureCredential(SECURE_AUTH_STORAGE_KEY, normalized);
    }
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    return;
  }
  if (!normalized) {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(AUTH_STORAGE_KEY, normalized);
}

// 把非 2xx HTTP 响应解析成 AppHttpError。
async function parseError(response: Response): Promise<AppHttpError> {
  const requestId = response.headers.get("x-request-id") ?? undefined;
  try {
    const body = (await response.json()) as ErrorEnvelope;
    if (body?.error?.code && body?.error?.message) {
      const details = body.error.details ?? {};
      return toHttpError({
        code: body.error.code,
        message: body.error.message,
        status: response.status,
        requestId: typeof details.request_id === "string" ? details.request_id : requestId,
        retryable: Boolean(details.retryable),
        details,
      });
    }
  } catch {
    // 响应体不是标准错误 JSON 时，使用通用 HTTP 错误。
  }
  return toHttpError({
    code: "HTTP_ERROR",
    message: `request_failed_${response.status}`,
    status: response.status,
    requestId,
  });
}

// requestJson 的扩展参数：支持 JSON body、超时和是否强制认证。
type RequestJsonInit = Omit<RequestInit, "body"> & {
  body?: unknown;
  timeoutMs?: number;
  authRequired?: boolean;
};

// 统一 JSON 请求入口：自动加 token、request id、超时和错误规范化。
export async function requestJson<T>(url: string, init?: RequestJsonInit): Promise<T> {
  const controller = new AbortController();
  const timeoutMs = init?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const requestId = randomRequestId();

  try {
    const token = getAuthToken();
    if (init?.authRequired !== false && !token) {
      throw toHttpError({
        code: "AUTH_TOKEN_MISSING",
        message: "Authentication token is missing.",
        status: 401,
        requestId,
      });
    }

    const hasBody = typeof init?.body !== "undefined";
    const headers = new Headers(init?.headers ?? {});
    headers.set("X-Request-ID", requestId);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    if (hasBody && !(init?.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(url, {
      ...init,
      body:
        hasBody && !(init?.body instanceof FormData)
          ? JSON.stringify(init.body)
          : (init?.body as BodyInit | undefined),
      headers,
      signal: controller.signal,
    });
    if (!response.ok) {
      throw await parseError(response);
    }
    return (await response.json()) as T;
  } catch (error) {
    if ((error as AppHttpError)?.code) {
      throw error;
    }
    if ((error as Error).name === "AbortError") {
      throw toHttpError({
        code: "NETWORK_TIMEOUT",
        message: "request_timeout",
        status: 408,
        requestId,
        retryable: true,
      });
    }
    throw toHttpError({
      code: "NETWORK_ERROR",
      message: "network_unreachable",
      status: 0,
      requestId,
      retryable: true,
      details: { cause: error instanceof Error ? error.message : String(error) },
    });
  } finally {
    window.clearTimeout(timer);
  }
}
