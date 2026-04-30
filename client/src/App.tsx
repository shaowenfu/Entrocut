import { useEffect, useState } from "react";
import LaunchpadPage from "./pages/LaunchpadPage";
import WorkspacePage from "./pages/WorkspacePage";
import {
  getCoreBaseUrlFromElectron,
  getCoreRuntimeState,
  isElectronEnvironment,
  isLikelyElectronShell,
  subscribeAuthDeepLink,
  subscribeCoreRuntimeState,
  type CoreRuntimeState,
} from "./services/electronBridge";
import { setRuntimeCoreBaseUrl } from "./services/coreClient";
import { useAuthStore } from "./store/useAuthStore";
import { useLaunchpadStore } from "./store/useLaunchpadStore";

const claimedWebLoginSessionIds = new Set<string>();

function getPendingWebLoginSessionId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const url = new URL(window.location.href);
  if (url.searchParams.get("auth_client") === "electron_polling") {
    return null;
  }
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

function DesktopBootstrapGate({ state }: { state: CoreRuntimeState | null }) {
  if (state?.status === "failed") {
    return (
      <main style={{ padding: 24, fontFamily: "Inter, system-ui, sans-serif" }}>
        <h2>本地 Core 服务启动失败</h2>
        <p>请重启应用；如果问题持续，请检查日志。</p>
        <pre>{state.lastError ?? "unknown_error"}</pre>
      </main>
    );
  }

  if (state?.status === "ready") {
    return null;
  }

  return (
    <main style={{ padding: 24, fontFamily: "Inter, system-ui, sans-serif" }}>
      <h2>正在启动本地核心服务…</h2>
      <p>首次启动可能需要几秒钟，请稍候。</p>
    </main>
  );
}

function App() {
  const [coreRuntimeState, setCoreRuntimeState] = useState<CoreRuntimeState | null>(null);
  const activeWorkspaceId = useLaunchpadStore((state) => state.activeWorkspaceId);
  const activeWorkspaceName = useLaunchpadStore((state) => state.activeWorkspaceName);
  const clearActiveWorkspace = useLaunchpadStore((state) => state.clearActiveWorkspace);
  const bootstrapAuth = useAuthStore((state) => state.bootstrap);
  const completeLoginFromDeepLink = useAuthStore((state) => state.completeLoginFromDeepLink);
  const pendingWebLoginSessionId = getPendingWebLoginSessionId();
  const isElectronShellWithoutBridge = isLikelyElectronShell() && !isElectronEnvironment();

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

  useEffect(() => {
    void getCoreRuntimeState().then((state) => {
      if (state?.baseUrl) {
        setRuntimeCoreBaseUrl(state.baseUrl);
      }
      setCoreRuntimeState(state);
    });

    void getCoreBaseUrlFromElectron().then((baseUrl) => {
      if (baseUrl) {
        setRuntimeCoreBaseUrl(baseUrl);
      }
    });

    const unsubscribe =
      subscribeCoreRuntimeState((state) => {
        if (state.baseUrl) {
          setRuntimeCoreBaseUrl(state.baseUrl);
        }
        setCoreRuntimeState(state);
      }) ?? undefined;

    return () => {
      unsubscribe?.();
    };
  }, []);

  if (isElectronShellWithoutBridge) {
    return (
      <main style={{ padding: 24, fontFamily: "Inter, system-ui, sans-serif" }}>
        <h2>Electron bridge unavailable</h2>
        <p>preload 未成功加载，无法读取本地视频文件路径。请重启桌面开发进程。</p>
      </main>
    );
  }

  if (isElectronEnvironment() && coreRuntimeState?.status !== "ready") {
    return <DesktopBootstrapGate state={coreRuntimeState} />;
  }

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
