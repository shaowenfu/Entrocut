import { useEffect } from "react";
import LaunchpadPage from "./pages/LaunchpadPage";
import WorkspacePage from "./pages/WorkspacePage";
import { subscribeAuthDeepLink } from "./services/electronBridge";
import { useAuthStore } from "./store/useAuthStore";
import { useLaunchpadStore } from "./store/useLaunchpadStore";

const claimedWebLoginSessionIds = new Set<string>();

function getPendingWebLoginSessionId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const url = new URL(window.location.href);
  const status = url.searchParams.get("auth_status");
  const loginSessionId = url.searchParams.get("auth_login_session_id");
  if (status !== "authenticated" || !loginSessionId) {
    return null;
  }
  if (!/^login_[a-z0-9]{16,64}$/i.test(loginSessionId)) {
    return null;
  }
  return loginSessionId;
}

function App() {
  const activeWorkspaceId = useLaunchpadStore((state) => state.activeWorkspaceId);
  const activeWorkspaceName = useLaunchpadStore((state) => state.activeWorkspaceName);
  const clearActiveWorkspace = useLaunchpadStore((state) => state.clearActiveWorkspace);
  const bootstrapAuth = useAuthStore((state) => state.bootstrap);
  const completeLoginFromDeepLink = useAuthStore((state) => state.completeLoginFromDeepLink);
  const pendingWebLoginSessionId = getPendingWebLoginSessionId();

  useEffect(() => {
    if (pendingWebLoginSessionId) {
      return;
    }
    void bootstrapAuth();
  }, [bootstrapAuth, pendingWebLoginSessionId]);

  useEffect(() => {
    const unsubscribe =
      subscribeAuthDeepLink((payload) => {
        void completeLoginFromDeepLink(payload.loginSessionId);
      }) ?? undefined;
    return () => {
      unsubscribe?.();
    };
  }, [completeLoginFromDeepLink]);

  useEffect(() => {
    if (!pendingWebLoginSessionId) {
      return;
    }
    if (claimedWebLoginSessionIds.has(pendingWebLoginSessionId)) {
      return;
    }
    claimedWebLoginSessionIds.add(pendingWebLoginSessionId);
    void completeLoginFromDeepLink(pendingWebLoginSessionId).finally(() => {
      const url = new URL(window.location.href);
      url.searchParams.delete("auth_login_session_id");
      url.searchParams.delete("auth_status");
      window.history.replaceState({}, "", url.toString());
    });
  }, [completeLoginFromDeepLink, pendingWebLoginSessionId]);

  if (!activeWorkspaceId) {
    return <LaunchpadPage />;
  }

  return (
    <WorkspacePage
      workspaceId={activeWorkspaceId}
      workspaceName={activeWorkspaceName ?? activeWorkspaceId}
      onBackLaunchpad={clearActiveWorkspace}
    />
  );
}

export default App;
