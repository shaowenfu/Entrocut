import { isElectronEnvironment } from "./electronBridge";
import { clearCoreAuthSession, syncCoreAuthSession } from "./coreClient";
import { getAuthToken, persistAuthToken, requestJson } from "./httpClient";

const SERVER_BASE_URL = (
  (import.meta.env as Record<string, string | undefined>).VITE_SERVER_BASE_URL?.trim() ||
  "http://127.0.0.1:8001"
).replace(/\/$/, "");

const REFRESH_STORAGE_KEY = "ENTROCUT_REFRESH_TOKEN";
const SECURE_REFRESH_STORAGE_KEY = "entrocut.auth.refresh_token";

let cachedRefreshToken: string | null = null;
let refreshStorageInitialized = false;

export interface AuthUser {
  id: string;
  email?: string | null;
  display_name?: string | null;
  avatar_url?: string | null;
  status: string;
  credits_balance: number;
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
  if (cachedRefreshToken && cachedRefreshToken.trim()) {
    return cachedRefreshToken.trim();
  }
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(REFRESH_STORAGE_KEY)?.trim() || null;
}

export function setRefreshToken(token: string | null): void {
  const normalized = token?.trim() || null;
  cachedRefreshToken = normalized;
  if (typeof window === "undefined") {
    return;
  }
}

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

export async function createGithubLoginSession(): Promise<LoginSessionCreateResponse> {
  const clientRedirectUri =
    isElectronEnvironment() || typeof window === "undefined"
      ? undefined
      : `${window.location.origin}/`;
  return requestJson<LoginSessionCreateResponse>(endpoint("/api/v1/auth/login-sessions"), {
    method: "POST",
    authRequired: false,
    body: {
      provider: "github",
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
  await persistAuthToken(response.result.access_token);
  await persistRefreshToken(response.result.refresh_token);
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
  await persistAuthToken(response.access_token);
  await persistRefreshToken(response.refresh_token);
  await syncCoreAuthSession(response.access_token);
  return response.access_token;
}

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
