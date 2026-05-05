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
  type RuntimeProviderItem,
  waitForLoginSession,
} from "../services/authClient";
import { deleteSecureCredential, getSecureCredential, openExternalUrl, setSecureCredential } from "../services/electronBridge";
import { getAuthToken, initializeAuthTokenStorage, persistAuthToken } from "../services/httpClient";

type AuthStatus = "idle" | "authenticating" | "authenticated" | "anonymous" | "error";

type RoutingMode = "Platform" | "BYOK";
type ModelCatalogState = "idle" | "loading" | "ready" | "failed";

interface ModelPreferences {
  byokKey: string;
  routingMode: RoutingMode;
  platformProvider: string;
  platformModel: string;
  platformCustomModel: string;
  byokProvider: string;
  byokModel: string;
  byokCustomModel: string;
  byokKeySavedByProvider: Record<string, boolean>;
}

interface AuthStoreState {
  status: AuthStatus;
  user: AuthUser | null;
  lastError: string | null;
  isRefreshingUser: boolean;
  platformModels: RuntimeModelItem[];
  platformProviders: RuntimeProviderItem[];
  modelCatalogState: ModelCatalogState;
  modelCatalogWarning: string | null;
  modelPrefs: ModelPreferences;
  bootstrap: () => Promise<void>;
  startGoogleLogin: () => Promise<void>;
  startGithubLogin: () => Promise<void>;
  completeLoginFromDeepLink: (loginSessionId: string) => Promise<void>;
  refreshUser: () => Promise<void>;
  refreshModelCatalog: () => Promise<void>;
  loadByokProviderKey: (provider: string) => Promise<void>;
  saveByokProviderKey: (provider: string, key: string) => Promise<void>;
  deleteByokProviderKey: (provider: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
  setModelPrefs: (patch: Partial<ModelPreferences>) => void;
}

const MODEL_PREFS_KEY = "ENTROCUT_MODEL_PREFS";
const DEFAULT_PLATFORM_PROVIDER = "deepseek";
const DEFAULT_PLATFORM_MODEL = "deepseek-chat";
const DEFAULT_BYOK_PROVIDER = "deepseek";
const DEFAULT_BYOK_MODEL = "deepseek-chat";

function byokCredentialId(provider: string): string {
  return `entrocut.byok.${provider}.api_key`;
}

function defaultModelPrefs(): ModelPreferences {
  return {
    byokKey: "",
    routingMode: "Platform",
    platformProvider: DEFAULT_PLATFORM_PROVIDER,
    platformModel: DEFAULT_PLATFORM_MODEL,
    platformCustomModel: "",
    byokProvider: DEFAULT_BYOK_PROVIDER,
    byokModel: DEFAULT_BYOK_MODEL,
    byokCustomModel: "",
    byokKeySavedByProvider: {},
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
      byokKey: "",
      routingMode: parsed.routingMode === "BYOK" ? "BYOK" : "Platform",
      platformProvider: parsed.platformProvider?.trim() || defaults.platformProvider,
      platformModel: parsed.platformModel?.trim() || defaults.platformModel,
      platformCustomModel: parsed.platformCustomModel?.trim() || "",
      byokProvider: parsed.byokProvider?.trim() || defaults.byokProvider,
      byokModel: parsed.byokModel?.trim() || defaults.byokModel,
      byokCustomModel: parsed.byokCustomModel?.trim() || "",
      byokKeySavedByProvider: parsed.byokKeySavedByProvider ?? {},
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
  platformProviders: [],
  modelCatalogState: "idle",
  modelCatalogWarning: null,
  modelPrefs: loadModelPrefs(),

  bootstrap: async () => {
    const currentPrefs = loadModelPrefs();
    if (currentPrefs.routingMode === "BYOK") {
      try {
        const key = (await getSecureCredential(byokCredentialId(currentPrefs.byokProvider)))?.trim() || "";
        set((state) => ({
          modelPrefs: {
            ...state.modelPrefs,
            byokKey: key,
            byokKeySavedByProvider: {
              ...state.modelPrefs.byokKeySavedByProvider,
              [currentPrefs.byokProvider]: Boolean(key),
            },
          },
        }));
      } catch {
        // BYOK key loading failure should not block auth bootstrap.
      }
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
      const platformProviders = catalog.providers ?? [];
      const platformModels = platformProviders.flatMap((provider) => provider.models ?? []);
      set((state) => {
        const selectedModelAvailable = platformProviders
          .find((provider) => provider.id === state.modelPrefs.platformProvider)
          ?.models.some((model) => model.id === state.modelPrefs.platformModel);
        const shouldUseDefault = state.modelPrefs.routingMode === "Platform" && !selectedModelAvailable;
        const nextPrefs = shouldUseDefault
          ? {
              ...state.modelPrefs,
              platformProvider: catalog.default_provider || DEFAULT_PLATFORM_PROVIDER,
              platformModel: catalog.default_model || DEFAULT_PLATFORM_MODEL,
            }
          : state.modelPrefs;
        if (nextPrefs !== state.modelPrefs) {
          persistModelPrefs(nextPrefs);
        }
        return {
          platformModels,
          platformProviders,
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

  loadByokProviderKey: async (provider) => {
    const normalizedProvider = provider.trim() || DEFAULT_BYOK_PROVIDER;
    try {
      const key = (await getSecureCredential(byokCredentialId(normalizedProvider)))?.trim() || "";
      set((state) => ({
        modelPrefs: {
          ...state.modelPrefs,
          byokProvider: normalizedProvider,
          byokKey: key,
          byokKeySavedByProvider: {
            ...state.modelPrefs.byokKeySavedByProvider,
            [normalizedProvider]: Boolean(key),
          },
        },
      }));
    } catch (error) {
      set({ lastError: errorMessage(error, "byok_key_load_failed") });
    }
  },

  saveByokProviderKey: async (provider, key) => {
    const normalizedProvider = provider.trim() || DEFAULT_BYOK_PROVIDER;
    const normalizedKey = key.trim();
    if (!normalizedKey) {
      set({ lastError: "BYOK API key is required." });
      return;
    }
    try {
      await setSecureCredential(byokCredentialId(normalizedProvider), normalizedKey);
      const persistedKey = (await getSecureCredential(byokCredentialId(normalizedProvider)))?.trim() || "";
      if (persistedKey !== normalizedKey) {
        throw new Error("Secure credential store is unavailable.");
      }
      set((state) => {
        const next = {
          ...state.modelPrefs,
          byokProvider: normalizedProvider,
          byokKey: normalizedKey,
          byokKeySavedByProvider: {
            ...state.modelPrefs.byokKeySavedByProvider,
            [normalizedProvider]: true,
          },
        };
        persistModelPrefs(next);
        return { modelPrefs: next, lastError: null };
      });
    } catch (error) {
      set({ lastError: errorMessage(error, "byok_key_save_failed") });
    }
  },

  deleteByokProviderKey: async (provider) => {
    const normalizedProvider = provider.trim() || DEFAULT_BYOK_PROVIDER;
    try {
      await deleteSecureCredential(byokCredentialId(normalizedProvider));
      set((state) => {
        const next = {
          ...state.modelPrefs,
          byokKey: state.modelPrefs.byokProvider === normalizedProvider ? "" : state.modelPrefs.byokKey,
          byokKeySavedByProvider: {
            ...state.modelPrefs.byokKeySavedByProvider,
            [normalizedProvider]: false,
          },
        };
        persistModelPrefs(next);
        return { modelPrefs: next, lastError: null };
      });
    } catch (error) {
      set({ lastError: errorMessage(error, "byok_key_delete_failed") });
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
