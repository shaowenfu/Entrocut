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

// 记录已处理过的网页登录会话，避免 React effect 重复兑换同一个 login session。
const claimedWebLoginSessionIds = new Set<string>();

// 从当前 URL 中解析网页登录回跳带回的 login session id。
function getPendingWebLoginSessionId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const url = new URL(window.location.href);
  // Electron 轮询登录页不由当前 Web 页面接管。
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

// 桌面端 core 尚未 ready 时的启动/失败占位页。
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

// Renderer 根组件：处理登录、core 启动状态和页面切换。
function App() {
  // Electron main 上报的本地 core 运行状态。
  const [coreRuntimeState, setCoreRuntimeState] = useState<CoreRuntimeState | null>(null);
  // 当前打开的 workspace；为空时显示 Launchpad。
  const activeWorkspaceId = useLaunchpadStore((state) => state.activeWorkspaceId);
  // 当前 workspace 展示名。
  const activeWorkspaceName = useLaunchpadStore((state) => state.activeWorkspaceName);
  // 返回 Launchpad 时清空当前 workspace。
  const clearActiveWorkspace = useLaunchpadStore((state) => state.clearActiveWorkspace);
  // 初始化登录态：读取本地 token 并拉取当前用户。
  const bootstrapAuth = useAuthStore((state) => state.bootstrap);
  // 用 deep link 或网页登录回跳的 login session 完成登录。
  const completeLoginFromDeepLink = useAuthStore((state) => state.completeLoginFromDeepLink);
  // Web 登录完成后 URL 中等待兑换的 login session。
  const pendingWebLoginSessionId = getPendingWebLoginSessionId();
  // 命中了 Electron 外壳特征，但 preload bridge 没挂载，说明桌面桥接失败。
  const isElectronShellWithoutBridge = isLikelyElectronShell() && !isElectronEnvironment();

  // 非网页登录回跳场景，正常启动登录态。
  useEffect(() => {
    if (pendingWebLoginSessionId) {
      return;
    }
    void bootstrapAuth();
  }, [bootstrapAuth, pendingWebLoginSessionId]);

  // 监听 Electron deep link 登录完成事件。
  useEffect(() => {
    const unsubscribe =
      subscribeAuthDeepLink((payload) => {
        void completeLoginFromDeepLink(payload.loginSessionId);
      }) ?? undefined;
    return () => {
      unsubscribe?.();
    };
  }, [completeLoginFromDeepLink]);

  // 处理浏览器网页登录回跳，并清理 URL 中的一次性参数。
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

  // 同步 Electron main 管理的 core 地址和运行状态。
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

  // Electron bridge 缺失时直接阻断，避免后续文件能力静默失效。
  if (isElectronShellWithoutBridge) {
    return (
      <main style={{ padding: 24, fontFamily: "Inter, system-ui, sans-serif" }}>
        <h2>Electron bridge unavailable</h2>
        <p>preload 未成功加载，无法读取本地视频文件路径。请重启桌面开发进程。</p>
      </main>
    );
  }

  // 桌面端必须等本地 core ready 后再进入业务页面。
  if (isElectronEnvironment() && coreRuntimeState?.status !== "ready") {
    return <DesktopBootstrapGate state={coreRuntimeState} />;
  }

  // 未选择 workspace 时显示启动页。
  if (!activeWorkspaceId) {
    return <LaunchpadPage />;
  }

  // 已选择 workspace 时进入主工作台。
  return (
    <WorkspacePage
      workspaceId={activeWorkspaceId}
      workspaceName={activeWorkspaceName ?? activeWorkspaceId}
      onBackLaunchpad={clearActiveWorkspace}
    />
  );
}

export default App;
