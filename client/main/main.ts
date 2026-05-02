import path from "node:path";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { app, BrowserWindow, ipcMain, safeStorage, shell } from "electron";
import { getCoreRuntimeState, onCoreRuntimeState, startCore, stopCore } from "./coreSupervisor";
import { registerFileScannerIpcHandlers } from "./fileScanner";
import {
  registerLocalMediaProtocolHandlers,
  registerLocalMediaProtocolScheme,
} from "./localMediaProtocol";

// ESM 下补出当前文件路径，供 Electron 资源定位使用。
const __filename = fileURLToPath(import.meta.url);
// 当前 main bundle 所在目录，用于定位 preload 和图标资源。
const __dirname = path.dirname(__filename);
// Renderer 页面地址；开发态默认指向 Vite Dev Server。
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? "http://127.0.0.1:5173";
// 桌面登录回调使用的自定义协议。
const AUTH_PROTOCOL = "entrocut";
// 加密 credential 存储文件名，实际目录在 app.getPath("userData")。
const SECURE_STORE_FILE = "secure-credentials.bin";
// 开发态无法加密时的明文 fallback 文件名。
const DEV_CREDENTIAL_STORE_FILE = "secure-credentials.dev.json";

// 当前唯一主窗口引用，用于派发 IPC 事件和控制窗口焦点。
let mainWindow: BrowserWindow | null = null;
// 窗口未就绪前收到的 deep link 暂存队列。
const pendingDeepLinks: string[] = [];

type SecureCredentialMap = Record<string, string>;

// 自定义媒体协议必须在 app ready 前声明权限。
registerLocalMediaProtocolScheme();

if (!app.isPackaged) {
  // 开发态关闭 GPU，减少 WSL/远程桌面环境下的渲染兼容问题。
  app.disableHardwareAcceleration();
  app.commandLine.appendSwitch("disable-gpu");
  app.commandLine.appendSwitch("disable-software-rasterizer");
}

if (!app.requestSingleInstanceLock()) {
  // 保持单实例运行，新的启动请求交给已有实例处理。
  app.quit();
}

// 注册 entrocut:// 协议，让系统能把登录回调转回本应用。
function registerProtocolClient(): void {
  if (process.defaultApp) {
    if (process.argv.length >= 2) {
      app.setAsDefaultProtocolClient(AUTH_PROTOCOL, process.execPath, [path.resolve(process.argv[1]!)]);
    }
    return;
  }
  app.setAsDefaultProtocolClient(AUTH_PROTOCOL);
}

// 从启动参数里提取系统转发来的 deep link。
function extractDeepLinkFromArgv(argv: string[]): string | null {
  for (const arg of argv) {
    if (typeof arg === "string" && arg.startsWith(`${AUTH_PROTOCOL}://`)) {
      return arg;
    }
  }
  return null;
}

// 校验并解析登录 deep link，只接受约定的 auth callback。
function parseDeepLink(rawUrl: string): { loginSessionId: string; status: "authenticated" } | null {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return null;
  }

  if (parsed.protocol !== `${AUTH_PROTOCOL}:`) {
    return null;
  }
  if (parsed.hostname !== "auth" || parsed.pathname !== "/callback") {
    return null;
  }

  const status = parsed.searchParams.get("status");
  const loginSessionId = parsed.searchParams.get("login_session_id");
  if (status !== "authenticated" || !loginSessionId) {
    return null;
  }
  if (!/^login_[a-z0-9]{16,64}$/i.test(loginSessionId)) {
    return null;
  }

  return {
    loginSessionId,
    status: "authenticated",
  };
}

// 把登录 deep link 派发给 Renderer；窗口未就绪时先入队。
function dispatchDeepLink(rawUrl: string): void {
  const payload = parseDeepLink(rawUrl);
  if (!payload) {
    return;
  }
  if (!mainWindow || mainWindow.isDestroyed()) {
    pendingDeepLinks.push(rawUrl);
    return;
  }
  mainWindow.webContents.send("auth:deep-link", payload);
}

// 窗口创建后补发此前暂存的 deep link。
function flushPendingDeepLinks(): void {
  while (pendingDeepLinks.length > 0) {
    const rawUrl = pendingDeepLinks.shift();
    if (rawUrl) {
      dispatchDeepLink(rawUrl);
    }
  }
}

// 统一显示并聚焦窗口，避免创建后窗口停留在后台。
function revealWindow(window: BrowserWindow): void {
  if (window.isDestroyed()) {
    return;
  }
  if (window.isMinimized()) {
    window.restore();
  }
  window.center();
  window.show();
  window.focus();
}

// 创建 Electron 主窗口，并加载 Renderer 页面。
function createMainWindow(coreBaseUrl: string | null): BrowserWindow {
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    autoHideMenuBar: true,
    show: false,
    backgroundColor: "#f6f7f9",
    icon: path.join(__dirname, "../public/icon.svg"),
    webPreferences: {
      // preload 是 Renderer 访问受控桌面能力的唯一桥。
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  void window.loadURL(DEV_SERVER_URL);
  window.once("ready-to-show", () => {
    revealWindow(window);
  });
  window.webContents.once("did-finish-load", () => {
    // 页面加载后立即同步当前 core 状态，避免 Renderer 等待下一次事件。
    window.webContents.send("core:runtime-state", getCoreRuntimeState());
    if (coreBaseUrl) {
      window.webContents.send("core:runtime-base-url", coreBaseUrl);
    }
    revealWindow(window);
  });
  mainWindow = window;
  window.on("closed", () => {
    if (mainWindow === window) {
      mainWindow = null;
    }
  });
  return window;
}

// 加密 credential 文件的完整路径。
function secureStorePath(): string {
  return path.join(app.getPath("userData"), SECURE_STORE_FILE);
}

// 开发态明文 credential fallback 文件的完整路径。
function devCredentialStorePath(): string {
  return path.join(app.getPath("userData"), DEV_CREDENTIAL_STORE_FILE);
}

// 当前系统是否支持 Electron safeStorage 加密。
function canUseEncryptedCredentialStore(): boolean {
  return safeStorage.isEncryptionAvailable();
}

// 仅开发态允许在 safeStorage 不可用时退回明文文件。
function canUsePlaintextDevCredentialStore(): boolean {
  return !app.isPackaged && !canUseEncryptedCredentialStore();
}

// 读取 credential map；生产优先加密文件，开发可退回明文 JSON。
async function readSecureCredentialMap(): Promise<SecureCredentialMap> {
  if (canUsePlaintextDevCredentialStore()) {
    try {
      const raw = await fs.readFile(devCredentialStorePath(), "utf8");
      const parsed = JSON.parse(raw) as unknown;
      return parsed && typeof parsed === "object" ? (parsed as SecureCredentialMap) : {};
    } catch (error) {
      const code = (error as NodeJS.ErrnoException | undefined)?.code;
      if (code === "ENOENT") {
        return {};
      }
      return {};
    }
  }

  try {
    const encrypted = await fs.readFile(secureStorePath());
    if (encrypted.length === 0) {
      return {};
    }
    const decrypted = safeStorage.decryptString(encrypted);
    const parsed = JSON.parse(decrypted) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as SecureCredentialMap) : {};
  } catch (error) {
    const code = (error as NodeJS.ErrnoException | undefined)?.code;
    if (code === "ENOENT") {
      return {};
    }
    return {};
  }
}

// 写入 credential map；和读取路径保持同一套加密/fallback 策略。
async function writeSecureCredentialMap(values: SecureCredentialMap): Promise<void> {
  const serialized = JSON.stringify(values);
  if (canUsePlaintextDevCredentialStore()) {
    await fs.mkdir(path.dirname(devCredentialStorePath()), { recursive: true });
    await fs.writeFile(devCredentialStorePath(), serialized);
    return;
  }
  const encrypted = safeStorage.encryptString(serialized);
  await fs.mkdir(path.dirname(secureStorePath()), { recursive: true });
  await fs.writeFile(secureStorePath(), encrypted);
}

// 判断当前是否是 WSL，且能调用 Windows 默认浏览器。
function canOpenWindowsDefaultBrowser(): boolean {
  if (process.platform === "win32") {
    return false;
  }
  if (!(process.env.WSL_DISTRO_NAME || process.env.WSL_INTEROP)) {
    return false;
  }
  return (
    existsSync("/mnt/c/WINDOWS/system32/cmd.exe") ||
    existsSync("/mnt/c/WINDOWS/System32/cmd.exe")
  );
}

// 在 WSL 中转调 Windows 默认浏览器打开外部 URL。
function openUrlInWindowsDefaultBrowser(rawUrl: string): boolean {
  const cmdPath = existsSync("/mnt/c/WINDOWS/System32/cmd.exe")
    ? "/mnt/c/WINDOWS/System32/cmd.exe"
    : "/mnt/c/WINDOWS/system32/cmd.exe";
  const child = spawn(
    cmdPath,
    ["/c", "start", "", rawUrl],
    {
      detached: true,
      stdio: "ignore",
      windowsHide: true,
    }
  );
  child.unref();
  return true;
}

// 注册本地文件选择和视频扫描相关 IPC。
registerFileScannerIpcHandlers();

// Renderer 请求打开外部网页登录地址。
ipcMain.handle("auth:open-external-url", async (_event, rawUrl: string) => {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error("invalid_external_url");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("unsupported_external_protocol");
  }
  try {
    if (canOpenWindowsDefaultBrowser()) {
      openUrlInWindowsDefaultBrowser(parsed.toString());
      return;
    }
    await shell.openExternal(parsed.toString());
  } catch {
    await shell.openExternal(parsed.toString());
  }
});

// Renderer 读取单个 credential。
ipcMain.handle("secure-store:get", async (_event, key: string) => {
  const values = await readSecureCredentialMap();
  const value = values[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
});

// Renderer 写入或清空单个 credential。
ipcMain.handle("secure-store:set", async (_event, key: string, value: string) => {
  const normalizedKey = key.trim();
  if (!normalizedKey) {
    throw new Error("invalid_secure_store_key");
  }
  const normalizedValue = value.trim();
  const values = await readSecureCredentialMap();
  if (!normalizedValue) {
    delete values[normalizedKey];
  } else {
    values[normalizedKey] = normalizedValue;
  }
  await writeSecureCredentialMap(values);
});

// Renderer 获取本地 core 当前运行状态。
ipcMain.handle("core:get-runtime-state", async () => {
  return getCoreRuntimeState();
});

// Renderer 获取本地 core base URL。
ipcMain.handle("core:get-base-url", async () => {
  return getCoreRuntimeState().baseUrl;
});

// Renderer 删除单个 credential。
ipcMain.handle("secure-store:delete", async (_event, key: string) => {
  const normalizedKey = key.trim();
  if (!normalizedKey) {
    return;
  }
  const values = await readSecureCredentialMap();
  delete values[normalizedKey];
  await writeSecureCredentialMap(values);
});

// 第二个应用实例启动时，把 deep link 转交给当前实例并聚焦窗口。
app.on("second-instance", (_event, argv) => {
  const deepLink = extractDeepLinkFromArgv(argv);
  if (deepLink) {
    dispatchDeepLink(deepLink);
  }
  if (mainWindow) {
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.focus();
  }
});

// macOS 下系统通过 open-url 事件传递自定义协议回调。
app.on("open-url", (event, url) => {
  event.preventDefault();
  dispatchDeepLink(url);
});

// 应用主启动流程：注册协议、创建窗口、启动 core、绑定生命周期。
app.whenReady().then(async () => {
  registerProtocolClient();
  registerLocalMediaProtocolHandlers();

  // core 状态变化时主动推送给 Renderer。
  const unsubscribeCoreRuntime = onCoreRuntimeState((state) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }
    mainWindow.webContents.send("core:runtime-state", state);
    if (state.baseUrl) {
      mainWindow.webContents.send("core:runtime-base-url", state.baseUrl);
    }
  });

  createMainWindow(getCoreRuntimeState().baseUrl);

  // 托管启动本地 core；失败由 Renderer 的 runtime state 展示。
  void startCore().catch((error) => {
    console.error("[core-supervisor] start failed", error);
  });

  const initialDeepLink = extractDeepLinkFromArgv(process.argv);
  if (initialDeepLink) {
    dispatchDeepLink(initialDeepLink);
  }
  flushPendingDeepLinks();

  // macOS 点击 Dock 图标时，如果无窗口则重建窗口。
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow(getCoreRuntimeState().baseUrl);
      flushPendingDeepLinks();
    }
  });

  // 退出前解除 core 状态监听，避免持有已销毁窗口引用。
  app.once("will-quit", () => {
    unsubscribeCoreRuntime();
  });
});

// 非 macOS 关闭所有窗口即退出应用，并同步停止本地 core。
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    void stopCore().finally(() => {
      app.quit();
    });
  }
});

// 任意退出路径都尝试停止本地 core。
app.on("before-quit", () => {
  void stopCore();
});
