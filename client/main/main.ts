import path from "node:path";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { app, BrowserWindow, ipcMain, safeStorage, shell } from "electron";
import { getCoreRuntimeState, onCoreRuntimeState, startCore, stopCore } from "./coreSupervisor";
import { registerFileScannerIpcHandlers } from "./fileScanner";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? "http://127.0.0.1:5173";
const AUTH_PROTOCOL = "entrocut";
const SECURE_STORE_FILE = "secure-credentials.bin";

let mainWindow: BrowserWindow | null = null;
const pendingDeepLinks: string[] = [];

type SecureCredentialMap = Record<string, string>;

if (!app.isPackaged) {
  app.disableHardwareAcceleration();
  app.commandLine.appendSwitch("disable-gpu");
  app.commandLine.appendSwitch("disable-software-rasterizer");
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
}

function registerProtocolClient(): void {
  if (process.defaultApp) {
    if (process.argv.length >= 2) {
      app.setAsDefaultProtocolClient(AUTH_PROTOCOL, process.execPath, [path.resolve(process.argv[1]!)]);
    }
    return;
  }
  app.setAsDefaultProtocolClient(AUTH_PROTOCOL);
}

function extractDeepLinkFromArgv(argv: string[]): string | null {
  for (const arg of argv) {
    if (typeof arg === "string" && arg.startsWith(`${AUTH_PROTOCOL}://`)) {
      return arg;
    }
  }
  return null;
}

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

function flushPendingDeepLinks(): void {
  while (pendingDeepLinks.length > 0) {
    const rawUrl = pendingDeepLinks.shift();
    if (rawUrl) {
      dispatchDeepLink(rawUrl);
    }
  }
}

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

function secureStorePath(): string {
  return path.join(app.getPath("userData"), SECURE_STORE_FILE);
}

async function readSecureCredentialMap(): Promise<SecureCredentialMap> {
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

async function writeSecureCredentialMap(values: SecureCredentialMap): Promise<void> {
  const serialized = JSON.stringify(values);
  const encrypted = safeStorage.encryptString(serialized);
  await fs.mkdir(path.dirname(secureStorePath()), { recursive: true });
  await fs.writeFile(secureStorePath(), encrypted);
}

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

registerFileScannerIpcHandlers();

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

ipcMain.handle("secure-store:get", async (_event, key: string) => {
  const values = await readSecureCredentialMap()
  const value = values[key]
  return typeof value === "string" && value.trim().length > 0 ? value : null
});

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


ipcMain.handle("core:get-runtime-state", async () => {
  return getCoreRuntimeState();
});

ipcMain.handle("core:get-base-url", async () => {
  return getCoreRuntimeState().baseUrl;
});
ipcMain.handle("secure-store:delete", async (_event, key: string) => {
  const normalizedKey = key.trim();
  if (!normalizedKey) {
    return;
  }
  const values = await readSecureCredentialMap();
  delete values[normalizedKey];
  await writeSecureCredentialMap(values);
});

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

app.on("open-url", (event, url) => {
  event.preventDefault();
  dispatchDeepLink(url);
});

app.whenReady().then(async () => {
  registerProtocolClient();

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

  void startCore().catch((error) => {
    console.error("[core-supervisor] start failed", error);
  });
  const initialDeepLink = extractDeepLinkFromArgv(process.argv);
  if (initialDeepLink) {
    dispatchDeepLink(initialDeepLink);
  }
  flushPendingDeepLinks();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow(getCoreRuntimeState().baseUrl);
      flushPendingDeepLinks();
    }
  });

  app.once("will-quit", () => {
    unsubscribeCoreRuntime();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    void stopCore().finally(() => {
      app.quit();
    });
  }
});

app.on("before-quit", () => {
  void stopCore();
});
