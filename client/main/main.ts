import path from "node:path";
import { fileURLToPath } from "node:url";

import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL ?? "http://127.0.0.1:5173";
const AUTH_PROTOCOL = "entrocut";

let mainWindow: BrowserWindow | null = null;
const pendingDeepLinks: string[] = [];

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

function createMainWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1180,
    minHeight: 760,
    autoHideMenuBar: true,
    icon: path.join(__dirname, "../public/icon.svg"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  void window.loadURL(DEV_SERVER_URL);
  mainWindow = window;
  window.on("closed", () => {
    if (mainWindow === window) {
      mainWindow = null;
    }
  });
  return window;
}

ipcMain.handle("dialog:open-directory", async () => {
  return dialog.showOpenDialog({
    title: "Select Media Folder",
    properties: ["openDirectory"],
  });
});

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
  await shell.openExternal(parsed.toString());
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

app.whenReady().then(() => {
  registerProtocolClient();
  createMainWindow();
  const initialDeepLink = extractDeepLinkFromArgv(process.argv);
  if (initialDeepLink) {
    dispatchDeepLink(initialDeepLink);
  }
  flushPendingDeepLinks();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
      flushPendingDeepLinks();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
