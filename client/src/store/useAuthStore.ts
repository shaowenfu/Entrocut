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
import { deleteSecureCredential, getSecureCredential, openExternalUrl, setSecureCredential } from "../services/electronBridge";
import { getAuthToken, initializeAuthTokenStorage, persistAuthToken } from "../services/httpClient";

type AuthStatus = "idle" | "authenticating" | "authenticated" | "anonymous" | "error";

type RoutingMode = "Platform" | "BYOK";
type ModelCatalogState = "idle" | "loading" | "ready" | "failed";

interface ModelPreferences {
  selectedModel: string;
  routingMode: RoutingMode;
  byokKey: string;
  byokModel: string;
  byokBaseUrl: string;
  byokChatPath: string;
  byokHeadersJson: string;
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
const BYOK_KEY_CREDENTIAL_ID = "entrocut.byok.api_key";
const DEFAULT_PLATFORM_MODEL = "entro-reasoning-v1";
const DEFAULT_BYOK_MODEL = "gpt-4o-mini";
const DEFAULT_BYOK_BASE_URL = "https://api.openai.com";
const DEFAULT_BYOK_CHAT_PATH = "/v1/chat/completions";
const DEFAULT_BYOK_HEADERS_JSON = "{}";

function defaultModelPrefs(): ModelPreferences {
  return {
    selectedModel: DEFAULT_PLATFORM_MODEL,
    routingMode: "Platform",
    byokKey: "",
    byokModel: DEFAULT_BYOK_MODEL,
    byokBaseUrl: DEFAULT_BYOK_BASE_URL,
    byokChatPath: DEFAULT_BYOK_CHAT_PATH,
    byokHeadersJson: DEFAULT_BYOK_HEADERS_JSON,
  };
}

function loadModelPrefs(): ModelPreferences {
  if (typeof window === "undefined") {
    return defaultModelPrefs();
  }
  try {
    const raw = window.localStorage.getItem(MODEL_PREFS_KEY);
    if (!raw) {
      return defaultModelPrefs();
    }
    const parsed = JSON.parse(raw) as Partial<ModelPreferences>;
    const defaults = defaultModelPrefs();
    return {
      selectedModel: parsed.selectedModel?.trim() || defaults.selectedModel,
      routingMode: parsed.routingMode === "BYOK" ? "BYOK" : "Platform",
      byokKey: "",
      byokModel: parsed.byokModel?.trim() || defaults.byokModel,
      byokBaseUrl: parsed.byokBaseUrl?.trim() || defaults.byokBaseUrl,
      byokChatPath: parsed.byokChatPath?.trim() || defaults.byokChatPath,
      byokHeadersJson: parsed.byokHeadersJson?.trim() || defaults.byokHeadersJson,
    };
  } catch {
    return defaultModelPrefs();
  }
}

function persistModelPrefs(prefs: ModelPreferences): void {
  if (typeof window === "undefined") {
    return;
  }
  const { byokKey: _byokKey, ...safePrefs } = prefs;
  window.localStorage.setItem(MODEL_PREFS_KEY, JSON.stringify(safePrefs));
}

async function persistByokKey(value: string): Promise<void> {
  const trimmed = value.trim();
  if (trimmed) {
    await setSecureCredential(BYOK_KEY_CREDENTIAL_ID, trimmed);
    return;
  }
  await deleteSecureCredential(BYOK_KEY_CREDENTIAL_ID);
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
    const storedByokKey = await getSecureCredential(BYOK_KEY_CREDENTIAL_ID);
    if (storedByokKey) {
      set((state) => ({ modelPrefs: { ...state.modelPrefs, byokKey: storedByokKey } }));
    }
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
    if (typeof patch.byokKey === "string") {
      void persistByokKey(patch.byokKey);
    }
    set((state) => {
      const next = { ...state.modelPrefs, ...patch };
      persistModelPrefs(next);
      return { modelPrefs: next };
    });
  },
}));
