export interface MediaPickInput {
  folderPath?: string;
  files?: File[];
}

export interface MediaPickResult {
  folderPath?: string;
  files?: File[];
}

export interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
}

export type MediaPickMode = "electron-folder" | "browser-files" | "auto";

function hasValidFiles(files?: File[]): files is File[] {
  return Array.isArray(files) && files.some((file) => file.size > 0);
}

export function isElectronEnvironment(): boolean {
  return typeof window !== "undefined" && typeof window.electron?.showOpenDirectory === "function";
}

export function normalizeMediaInput(input?: MediaPickInput): MediaPickResult | null {
  if (!input) {
    return null;
  }
  const folderPath = input.folderPath?.trim();
  const files = input.files?.filter((file) => file.size > 0);
  if (folderPath) {
    return { folderPath };
  }
  if (hasValidFiles(files)) {
    return { files };
  }
  return null;
}

export async function pickFolderFromElectron(): Promise<string | null> {
  const bridge = window.electron;
  if (!bridge?.showOpenDirectory) {
    return null;
  }
  const pickedPath = await bridge.showOpenDirectory();
  if (!pickedPath) {
    return null;
  }
  return pickedPath;
}

export async function pickVideoFilesFromBrowser(): Promise<File[] | null> {
  if (typeof document === "undefined") {
    return null;
  }

  return new Promise<File[] | null>((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.accept = "video/*,.mp4,.mov,.m4v,.webm,.mkv,.avi";
    input.style.display = "none";
    let settled = false;
    let cancelTimer: number | null = null;

    const cleanup = () => {
      if (cancelTimer !== null) {
        window.clearTimeout(cancelTimer);
        cancelTimer = null;
      }
      input.value = "";
      window.removeEventListener("focus", handleWindowFocus, true);
      input.remove();
    };

    const handleWindowFocus = () => {
      cancelTimer = window.setTimeout(() => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        resolve(null);
      }, 300);
    };

    input.onchange = () => {
      settled = true;
      const list = input.files ? Array.from(input.files) : [];
      cleanup();
      resolve(list.length > 0 ? list : null);
    };

    document.body.appendChild(input);
    window.addEventListener("focus", handleWindowFocus, true);
    input.click();
  });
}

export async function pickMediaFromSystem(): Promise<MediaPickResult | null> {
  const folderPath = await pickFolderFromElectron();
  if (folderPath) {
    return { folderPath };
  }
  const files = await pickVideoFilesFromBrowser();
  if (!files || files.length === 0) {
    return null;
  }
  return { files };
}

export async function pickMediaByMode(mode: MediaPickMode): Promise<MediaPickResult | null> {
  if (mode === "electron-folder") {
    const folderPath = await pickFolderFromElectron();
    return folderPath ? { folderPath } : null;
  }
  if (mode === "browser-files") {
    const files = await pickVideoFilesFromBrowser();
    return files && files.length > 0 ? { files } : null;
  }
  // auto: 保持原有 fallback 逻辑
  return pickMediaFromSystem();
}

export async function openExternalUrl(url: string): Promise<void> {
  if (typeof window === "undefined") {
    return;
  }
  const bridge = window.electron;
  if (bridge?.openExternalUrl) {
    await bridge.openExternalUrl(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

export async function getSecureCredential(key: string): Promise<string | null> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.getSecureCredential) {
    return null;
  }
  return bridge.getSecureCredential(key);
}

export async function setSecureCredential(key: string, value: string): Promise<void> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.setSecureCredential) {
    return;
  }
  await bridge.setSecureCredential(key, value);
}

export async function deleteSecureCredential(key: string): Promise<void> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.deleteSecureCredential) {
    return;
  }
  await bridge.deleteSecureCredential(key);
}

export function subscribeAuthDeepLink(
  callback: (payload: AuthDeepLinkPayload) => void
): (() => void) | null {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.onAuthDeepLink) {
    return null;
  }
  return bridge.onAuthDeepLink(callback);
}
