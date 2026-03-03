export type ServiceTarget = "core" | "server";
export type HealthState = "checking" | "online" | "offline";

export interface ServiceHealthSnapshot {
  state: HealthState;
  checkedAtMs: number | null;
  latencyMs: number | null;
  message: string | null;
}

interface HealthResponse {
  status?: string;
}

const REQUEST_TIMEOUT_MS = 1600;
const DEFAULT_BASE_URL: Record<ServiceTarget, string> = {
  core: "http://127.0.0.1:8000",
  server: "http://127.0.0.1:8001",
};

function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function getBaseUrl(target: ServiceTarget): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const envKey = target === "core" ? "VITE_CORE_BASE_URL" : "VITE_SERVER_BASE_URL";
  const fromEnv = env[envKey]?.trim();
  return trimTrailingSlash(fromEnv && fromEnv.length > 0 ? fromEnv : DEFAULT_BASE_URL[target]);
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "unknown_error";
}

async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

export function createInitialHealthSnapshot(): ServiceHealthSnapshot {
  return {
    state: "checking",
    checkedAtMs: null,
    latencyMs: null,
    message: null,
  };
}

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
