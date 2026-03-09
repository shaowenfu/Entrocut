import { create } from "zustand";
import {
  claimLoginSession,
  clearCoreAuthSessionState,
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

interface AuthStoreState {
  status: AuthStatus;
  user: AuthUser | null;
  lastError: string | null;
  bootstrap: () => Promise<void>;
  startGoogleLogin: () => Promise<void>;
  completeLoginFromDeepLink: (loginSessionId: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
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
}));
