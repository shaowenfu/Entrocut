// 可探测健康状态的服务目标。
export type ServiceTarget = "core" | "server";
// 前端展示用健康状态。
export type HealthState = "checking" | "online" | "offline";

// 单次健康检查快照。
export interface ServiceHealthSnapshot {
  state: HealthState;
  checkedAtMs: number | null;
  latencyMs: number | null;
  message: string | null;
}

// /health 接口响应。
interface HealthResponse {
  status?: string;
}

// 健康检查超时时间。
const REQUEST_TIMEOUT_MS = 1600;
// core/server 的默认本地地址。
const DEFAULT_BASE_URL: Record<ServiceTarget, string> = {
  core: "http://127.0.0.1:8000",
  server: "http://127.0.0.1:8001",
};

// 去掉 URL 末尾斜杠。
function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

// 根据目标服务读取 base URL，优先环境变量。
function getBaseUrl(target: ServiceTarget): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const envKey = target === "core" ? "VITE_CORE_BASE_URL" : "VITE_SERVER_BASE_URL";
  const fromEnv = env[envKey]?.trim();
  return trimTrailingSlash(fromEnv && fromEnv.length > 0 ? fromEnv : DEFAULT_BASE_URL[target]);
}

// 把未知异常转换成展示用错误消息。
function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "unknown_error";
}

// 带超时的 fetch。
async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

// 创建初始健康状态。
export function createInitialHealthSnapshot(): ServiceHealthSnapshot {
  return {
    state: "checking",
    checkedAtMs: null,
    latencyMs: null,
    message: null,
  };
}

// 探测 core 或 server 的 /health 状态。
export async function probeServiceHealth(target: ServiceTarget): Promise<ServiceHealthSnapshot> {
  const startedAt = performance.now();
  const url = `${getBaseUrl(target)}/health`;

  try {
    const response = await fetchWithTimeout(url, REQUEST_TIMEOUT_MS);
    const latencyMs = Math.round(performance.now() - startedAt);

    if (!response.ok) {
      return {
        state: "offline",
        checkedAtMs: Date.now(),
        latencyMs,
        message: `http_${response.status}`,
      };
    }

    const data = (await response.json()) as HealthResponse;
    if (data.status !== "ok") {
      return {
        state: "offline",
        checkedAtMs: Date.now(),
        latencyMs,
        message: `status_${data.status ?? "unknown"}`,
      };
    }

    return {
      state: "online",
      checkedAtMs: Date.now(),
      latencyMs,
      message: null,
    };
  } catch (error) {
    return {
      state: "offline",
      checkedAtMs: Date.now(),
      latencyMs: Math.round(performance.now() - startedAt),
      message: getErrorMessage(error),
    };
  }
}
