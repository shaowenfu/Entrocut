import { create } from "zustand";
import {
  claimLoginSession,
  clearCoreAuthSessionState,
  createGithubLoginSession,
  createGoogleLoginSession,
  fetchCurrentUser,
  fetchRuntimeModels,
  getRefreshToken,
  initializeRefreshTokenStorage,
  isDevLoginPollingEnabled,
  logoutCurrentUser,
  persistRefreshToken,
  refreshAccessToken,
  syncCoreAuthSessionState,
  type AuthUser,
  type RuntimeModelItem,
  waitForLoginSession,
} from "../services/authClient";
import { openExternalUrl } from "../services/electronBridge";
import { getAuthToken, initializeAuthTokenStorage, persistAuthToken } from "../services/httpClient";

type AuthStatus = "idle" | "authenticating" | "authenticated" | "anonymous" | "error";

type RoutingMode = "Platform" | "BYOK";
type ModelCatalogState = "idle" | "loading" | "ready" | "failed";

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
  isRefreshingUser: boolean;
  platformModels: RuntimeModelItem[];
  modelCatalogState: ModelCatalogState;
  modelCatalogWarning: string | null;
  modelPrefs: ModelPreferences;
  bootstrap: () => Promise<void>;
  startGoogleLogin: () => Promise<void>;
  startGithubLogin: () => Promise<void>;
  completeLoginFromDeepLink: (loginSessionId: string) => Promise<void>;
  refreshUser: () => Promise<void>;
  refreshModelCatalog: () => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
  setModelPrefs: (patch: Partial<ModelPreferences>) => void;
}

const MODEL_PREFS_KEY = "ENTROCUT_MODEL_PREFS";
const DEFAULT_PLATFORM_MODEL = "entro-reasoning-v1";

function loadModelPrefs(): ModelPreferences {
  if (typeof window === "undefined") {
    return { selectedModel: DEFAULT_PLATFORM_MODEL, routingMode: "Platform", byokKey: "", byokBaseUrl: "https://api.openai.com" };
  }
  try {
    const raw = window.localStorage.getItem(MODEL_PREFS_KEY);
    if (!raw) {
      return { selectedModel: DEFAULT_PLATFORM_MODEL, routingMode: "Platform", byokKey: "", byokBaseUrl: "https://api.openai.com" };
    }
    const parsed = JSON.parse(raw) as Partial<ModelPreferences>;
    return {
      selectedModel: parsed.selectedModel?.trim() || DEFAULT_PLATFORM_MODEL,
      routingMode: parsed.routingMode === "BYOK" ? "BYOK" : "Platform",
      byokKey: parsed.byokKey?.trim() || "",
      byokBaseUrl: parsed.byokBaseUrl?.trim() || "https://api.openai.com",
    };
  } catch {
    return { selectedModel: DEFAULT_PLATFORM_MODEL, routingMode: "Platform", byokKey: "", byokBaseUrl: "https://api.openai.com" };
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
  isRefreshingUser: false,
  platformModels: [],
  modelCatalogState: "idle",
  modelCatalogWarning: null,
  modelPrefs: loadModelPrefs(),

  bootstrap: async () => {
    await initializeAuthTokenStorage();
    await initializeRefreshTokenStorage();
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
      await persistAuthToken("");
      await persistRefreshToken(null);
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
      if (isDevLoginPollingEnabled()) {
        const user = await waitForLoginSession(session.login_session_id);
        set({
          status: "authenticated",
          user,
          lastError: null,
        });
      }
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
      if (isDevLoginPollingEnabled()) {
        const user = await waitForLoginSession(session.login_session_id);
        set({
          status: "authenticated",
          user,
          lastError: null,
        });
      }
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

  refreshUser: async () => {
    set({ isRefreshingUser: true, lastError: null });
    try {
      const user = await fetchCurrentUser();
      await syncCoreAuthSessionState(user.id);
      set({
        status: "authenticated",
        user,
        isRefreshingUser: false,
        lastError: null,
      });
    } catch (error) {
      set({
        isRefreshingUser: false,
        lastError: errorMessage(error, "user_refresh_failed"),
      });
    }
  },

  refreshModelCatalog: async () => {
    set({ modelCatalogState: "loading", modelCatalogWarning: null });
    try {
      const catalog = await fetchRuntimeModels();
      const platformModels = catalog.platform_models ?? [];
      set((state) => {
        const selectedModelAvailable = platformModels.some((model) => model.id === state.modelPrefs.selectedModel);
        const shouldUseDefault = state.modelPrefs.routingMode === "Platform" && !selectedModelAvailable;
        const nextPrefs = shouldUseDefault
          ? {
              ...state.modelPrefs,
              selectedModel: catalog.default_model || platformModels[0]?.id || DEFAULT_PLATFORM_MODEL,
            }
          : state.modelPrefs;
        if (nextPrefs !== state.modelPrefs) {
          persistModelPrefs(nextPrefs);
        }
        return {
          platformModels,
          modelCatalogState: "ready",
          modelCatalogWarning: catalog.warnings?.[0] ?? null,
          modelPrefs: nextPrefs,
        };
      });
    } catch (error) {
      set({
        modelCatalogState: "failed",
        modelCatalogWarning: errorMessage(error, "model_catalog_load_failed"),
      });
    }
  },

  logout: async () => {
    try {
      await logoutCurrentUser();
    } catch {
      await persistAuthToken("");
      await persistRefreshToken(null);
      await clearCoreAuthSessionState();
    }
    set({
      status: "anonymous",
      user: null,
      isRefreshingUser: false,
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
