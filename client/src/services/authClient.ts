import { isElectronEnvironment } from "./electronBridge";
import { clearCoreAuthSession, syncCoreAuthSession } from "./coreClient";
import { getAuthToken, requestJson, setAuthToken } from "./httpClient";

const SERVER_BASE_URL = (
  (import.meta.env as Record<string, string | undefined>).VITE_SERVER_BASE_URL?.trim() ||
  "http://127.0.0.1:8001"
).replace(/\/$/, "");

const REFRESH_STORAGE_KEY = "ENTROCUT_REFRESH_TOKEN";

export interface AuthUser {
  id: string;
  email?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  status: string;
  plan: string;
  quota_status: string;
}

interface LoginSessionCreateResponse {
  login_session_id: string;
  authorize_url: string;
  expires_in: number;
}

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

interface MeResponse {
  user: AuthUser;
}

interface RefreshResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

function endpoint(path: string): string {
  return `${SERVER_BASE_URL}${path}`;
}

export async function syncCoreAuthSessionState(userId?: string | null): Promise<void> {
  const token = getAuthToken();
  if (!token) {
    await clearCoreAuthSession();
    return;
  }
  await syncCoreAuthSession(token, userId);
}

export async function clearCoreAuthSessionState(): Promise<void> {
  await clearCoreAuthSession();
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(REFRESH_STORAGE_KEY)?.trim() || null;
}

export function setRefreshToken(token: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  const normalized = token?.trim();
  if (!normalized) {
    window.localStorage.removeItem(REFRESH_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(REFRESH_STORAGE_KEY, normalized);
}

export async function createGoogleLoginSession(): Promise<LoginSessionCreateResponse> {
  const clientRedirectUri =
    isElectronEnvironment() || typeof window === "undefined"
      ? undefined
      : `${window.location.origin}/`;
  return requestJson<LoginSessionCreateResponse>(endpoint("/api/v1/auth/login-sessions"), {
    method: "POST",
    authRequired: false,
    body: {
      provider: "google",
      client_redirect_uri: clientRedirectUri,
    },
  });
}

export async function claimLoginSession(loginSessionId: string): Promise<AuthUser> {
  const response = await requestJson<LoginSessionClaimResponse>(
    endpoint(`/api/v1/auth/login-sessions/${encodeURIComponent(loginSessionId)}`),
    {
      authRequired: false,
    }
  );
  if (!response.result?.access_token || !response.result.refresh_token) {
    throw {
      code: response.error?.code ?? "AUTH_LOGIN_SESSION_UNAVAILABLE",
      message: response.error?.message ?? "login_session_result_unavailable",
      status: 400,
    };
  }
  setAuthToken(response.result.access_token);
  setRefreshToken(response.result.refresh_token);
  await syncCoreAuthSession(response.result.access_token, response.result.user.id);
  return response.result.user;
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const response = await requestJson<MeResponse>(endpoint("/api/v1/me"));
  return response.user;
}

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
  setAuthToken(response.access_token);
  setRefreshToken(response.refresh_token);
  await syncCoreAuthSession(response.access_token);
  return response.access_token;
}

export async function logoutCurrentUser(): Promise<void> {
  try {
    await requestJson(endpoint("/api/v1/auth/logout"), {
      method: "POST",
    });
  } finally {
    setAuthToken("");
    setRefreshToken(null);
    await clearCoreAuthSession();
  }
}
