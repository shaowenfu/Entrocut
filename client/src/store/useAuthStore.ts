import { create } from "zustand";
import {
  claimLoginSession,
  clearCoreAuthSessionState,
  createGithubLoginSession,
  createGoogleLoginSession,
  fetchCurrentUser,
  getRefreshToken,
  logoutCurrentUser,
  refreshAccessToken,
  setRefreshToken,
  syncCoreAuthSessionState,
  type AuthUser,
} from "../services/authClient";
import { openExternalUrl } from "../services/electronBridge";
import { getAuthToken, setAuthToken } from "../services/httpClient";

type AuthStatus = "idle" | "authenticating" | "authenticated" | "anonymous" | "error";

type RoutingMode = "Platform" | "BYOK";

interface ModelPreferences {
  selectedModel: string;
  routingMode: RoutingMode;
  byokKey: string;
  byokBaseUrl: string;
}

interface AuthStoreState {
  status: AuthStatus;
  user: AuthUser | null;
  lastError: string | null;
  modelPrefs: ModelPreferences;
  bootstrap: () => Promise<void>;
  startGoogleLogin: () => Promise<void>;
  startGithubLogin: () => Promise<void>;
  completeLoginFromDeepLink: (loginSessionId: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
  setModelPrefs: (patch: Partial<ModelPreferences>) => void;
}

const MODEL_PREFS_KEY = "ENTROCUT_MODEL_PREFS";

function loadModelPrefs(): ModelPreferences {
  if (typeof window === "undefined") {
    return { selectedModel: "gpt-4o-mini", routingMode: "Platform", byokKey: "", byokBaseUrl: "https://api.openai.com" };
  }
  try {
    const raw = window.localStorage.getItem(MODEL_PREFS_KEY);
    if (!raw) {
      return { selectedModel: "gpt-4o-mini", routingMode: "Platform", byokKey: "", byokBaseUrl: "https://api.openai.com" };
    }
    const parsed = JSON.parse(raw) as Partial<ModelPreferences>;
    return {
      selectedModel: parsed.selectedModel?.trim() || "gpt-4o-mini",
      routingMode: parsed.routingMode === "BYOK" ? "BYOK" : "Platform",
      byokKey: parsed.byokKey?.trim() || "",
      byokBaseUrl: parsed.byokBaseUrl?.trim() || "https://api.openai.com",
    };
  } catch {
    return { selectedModel: "gpt-4o-mini", routingMode: "Platform", byokKey: "", byokBaseUrl: "https://api.openai.com" };
  }
}

function persistModelPrefs(prefs: ModelPreferences): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(MODEL_PREFS_KEY, JSON.stringify(prefs));
}

function errorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
    return error.message;
  }
  return fallback;
}

export const useAuthStore = create<AuthStoreState>((set) => ({
  status: "idle",
  user: null,
  lastError: null,
  modelPrefs: loadModelPrefs(),

  bootstrap: async () => {
    const accessToken = getAuthToken();
    const refreshToken = getRefreshToken();
    if (!accessToken && !refreshToken) {
      set({ status: "anonymous", user: null, lastError: null });
      return;
    }

    try {
      if (!accessToken && refreshToken) {
        await refreshAccessToken();
      }
      const user = await fetchCurrentUser();
      await syncCoreAuthSessionState(user.id);
      set({ status: "authenticated", user, lastError: null });
    } catch (error) {
      try {
        if (refreshToken) {
          await refreshAccessToken();
          const user = await fetchCurrentUser();
          await syncCoreAuthSessionState(user.id);
          set({ status: "authenticated", user, lastError: null });
          return;
        }
      } catch {
        // ignore fallback refresh failure
      }
      setAuthToken("");
      setRefreshToken(null);
      await clearCoreAuthSessionState();
      set({
        status: "anonymous",
        user: null,
        lastError: errorMessage(error, "auth_bootstrap_failed"),
      });
    }
  },

  startGoogleLogin: async () => {
    set({ status: "authenticating", lastError: null });
    try {
      const session = await createGoogleLoginSession();
      await openExternalUrl(session.authorize_url);
    } catch (error) {
      set({
        status: "error",
        lastError: errorMessage(error, "google_login_start_failed"),
      });
    }
  },

  startGithubLogin: async () => {
    set({ status: "authenticating", lastError: null });
    try {
      const session = await createGithubLoginSession();
      await openExternalUrl(session.authorize_url);
    } catch (error) {
      set({
        status: "error",
        lastError: errorMessage(error, "github_login_start_failed"),
      });
    }
  },

  completeLoginFromDeepLink: async (loginSessionId: string) => {
    set({ status: "authenticating", lastError: null });
    try {
      const user = await claimLoginSession(loginSessionId);
      set({
        status: "authenticated",
        user,
        lastError: null,
      });
    } catch (error) {
      set({
        status: "error",
        lastError: errorMessage(error, "google_login_complete_failed"),
      });
    }
  },

  logout: async () => {
    try {
      await logoutCurrentUser();
    } catch {
      setAuthToken("");
      setRefreshToken(null);
      await clearCoreAuthSessionState();
    }
    set({
      status: "anonymous",
      user: null,
      lastError: null,
    });
  },

  clearError: () => {
    set({ lastError: null });
  },

  setModelPrefs: (patch) => {
    set((state) => {
      const next = { ...state.modelPrefs, ...patch };
      persistModelPrefs(next);
      return { modelPrefs: next };
    });
  },
}));
