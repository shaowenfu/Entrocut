export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface AppHttpError {
  code: string;
  message: string;
  status: number;
  requestId?: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

const DEFAULT_TIMEOUT_MS = 10000;
const AUTH_STORAGE_KEY = "ENTROCUT_AUTH_TOKEN";

function randomRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `req_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  }
  const suffix = Math.random().toString(16).slice(2, 14);
  return `req_${suffix}`;
}

function toHttpError(error: AppHttpError): AppHttpError {
  return error;
}

export function getAuthToken(): string | null {
  const env = import.meta.env as Record<string, string | undefined>;
  const envToken = env.VITE_AUTH_TOKEN?.trim();
  if (envToken) {
    return envToken;
  }
  if (typeof window === "undefined") {
    return null;
  }
  const saved = window.localStorage.getItem(AUTH_STORAGE_KEY);
  return saved?.trim() || null;
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const normalized = token.trim();
  if (!normalized) {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(AUTH_STORAGE_KEY, normalized);
}

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
    // ignore parse error
  }
  return toHttpError({
    code: "HTTP_ERROR",
    message: `request_failed_${response.status}`,
    status: response.status,
    requestId,
  });
}

type RequestJsonInit = Omit<RequestInit, "body"> & {
  body?: unknown;
  timeoutMs?: number;
  authRequired?: boolean;
};

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
