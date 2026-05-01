export interface MediaPickInput {
  folderPath?: string;
  files?: Array<File | DesktopMediaFileReference>;
}

export interface MediaPickResult {
  folderPath?: string;
  files?: Array<File | DesktopMediaFileReference>;
}

export interface DesktopMediaFileReference {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
}

export interface LocalMediaRegistration {
  name: string;
  path: string;
  url: string;
  mime_type?: string;
}

export interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
}

export type CoreRuntimeStatus = "idle" | "starting" | "ready" | "failed" | "stopped";

export interface CoreRuntimeState {
  status: CoreRuntimeStatus;
  baseUrl: string | null;
  pid: number | null;
  lastError: string | null;
}

export type MediaPickMode = "electron-folder" | "electron-videos" | "electron-media" | "browser-files" | "auto";

function hasValidFiles(files?: Array<File | DesktopMediaFileReference>): files is Array<File | DesktopMediaFileReference> {
  return Array.isArray(files) && files.length > 0;
}

function isDesktopMediaFileReference(file: File | DesktopMediaFileReference): file is DesktopMediaFileReference {
  return "path" in file && typeof file.path === "string";
}

export function isElectronEnvironment(): boolean {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  return Boolean(
    bridge?.showOpenDirectory ||
    bridge?.showOpenVideos ||
    bridge?.showOpenMedia ||
    bridge?.getPathForFile ||
    bridge?.version
  );
}

export function isLikelyElectronShell(): boolean {
  if (typeof navigator === "undefined") {
    return false;
  }
  return navigator.userAgent.toLowerCase().includes("electron");
}

export function normalizeMediaInput(input?: MediaPickInput): MediaPickResult | null {
  if (!input) {
    return null;
  }
  const folderPath = input.folderPath?.trim();
  const files: Array<File | DesktopMediaFileReference> = [];
  for (const file of input.files ?? []) {
    if (isDesktopMediaFileReference(file)) {
      const normalizedPath = normalizePathForLocalCore(file.path.trim());
      if (normalizedPath.length > 0) {
        files.push({ ...file, path: normalizedPath });
      }
      continue;
    }
    if (file.size <= 0) {
      continue;
    }
    const desktopFile = toDesktopMediaFileReference(file);
    files.push(desktopFile ?? file);
  }
  if (hasValidFiles(files)) {
    return { files };
  }
  if (folderPath) {
    return { folderPath };
  }
  return null;
}

export async function pickFolderFromElectron(): Promise<MediaPickResult | null> {
  const bridge = window.electron;
  if (!bridge?.showOpenDirectory) {
    return null;
  }
  const picked = await bridge.showOpenDirectory();
  if (!picked) {
    return null;
  }
  if (picked.files.length > 0) {
    return { files: picked.files };
  }
  if (picked.folderPath) {
    return { folderPath: picked.folderPath };
  }
  return null;
}

export async function pickVideoFilesFromElectron(): Promise<MediaPickResult | null> {
  const bridge = window.electron;
  if (!bridge?.showOpenVideos) {
    return null;
  }
  const picked = await bridge.showOpenVideos();
  if (!picked || picked.files.length === 0) {
    return null;
  }
  return { files: picked.files };
}

export async function pickMediaFromElectron(): Promise<MediaPickResult | null> {
  const bridge = window.electron;
  if (!bridge?.showOpenMedia) {
    return pickVideoFilesFromElectron();
  }
  const picked = await bridge.showOpenMedia();
  if (!picked || picked.files.length === 0) {
    return null;
  }
  return { files: picked.files };
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

export function getPathForFile(file: File): string | null {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  const filePath =
    bridge?.getPathForFile?.(file) ??
    (file as File & { path?: string }).path ??
    "";
  const normalized = normalizePathForLocalCore(filePath.trim());
  return normalized.length > 0 ? normalized : null;
}

export function normalizePathForLocalCore(nativePath: string): string {
  const wslMatch = nativePath.match(/^\\\\wsl(?:\.localhost|\$)\\[^\\]+\\(.+)$/i);
  if (!wslMatch) {
    return nativePath;
  }
  return `/${wslMatch[1]!.replaceAll("\\", "/")}`;
}

export function toDesktopMediaFileReference(file: File): DesktopMediaFileReference | null {
  const filePath = getPathForFile(file);
  if (!filePath) {
    return null;
  }
  return {
    name: file.name,
    path: filePath,
    size_bytes: file.size,
    mime_type: file.type || undefined,
  };
}

export function toDesktopMediaFileReferences(files: File[]): DesktopMediaFileReference[] {
  const references: DesktopMediaFileReference[] = [];
  for (const file of files) {
    const reference = toDesktopMediaFileReference(file);
    if (reference) {
      references.push(reference);
    }
  }
  return references;
}

export async function pickMediaFromSystem(): Promise<MediaPickResult | null> {
  if (isElectronEnvironment()) {
    return pickMediaFromElectron();
  }
  const mediaFromElectron = await pickFolderFromElectron();
  if (mediaFromElectron) {
    return mediaFromElectron;
  }
  const files = await pickVideoFilesFromBrowser();
  if (!files || files.length === 0) {
    return null;
  }
  return { files };
}

export async function pickMediaByMode(mode: MediaPickMode): Promise<MediaPickResult | null> {
  if (mode === "electron-folder") {
    return pickFolderFromElectron();
  }
  if (mode === "electron-videos") {
    return pickVideoFilesFromElectron();
  }
  if (mode === "electron-media") {
    return pickMediaFromElectron();
  }
  if (mode === "browser-files") {
    const files = await pickVideoFilesFromBrowser();
    return files && files.length > 0 ? { files } : null;
  }
  // auto: 保持原有 fallback 逻辑
  return pickMediaFromSystem();
}

export async function registerLocalMediaFiles(
  files: DesktopMediaFileReference[]
): Promise<LocalMediaRegistration[]> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.registerLocalMediaFiles) {
    return [];
  }
  return bridge.registerLocalMediaFiles(files);
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


export async function getCoreRuntimeState(): Promise<CoreRuntimeState | null> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.getCoreRuntimeState) {
    return null;
  }
  return bridge.getCoreRuntimeState();
}

export async function getCoreBaseUrlFromElectron(): Promise<string | null> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.getCoreBaseUrl) {
    return null;
  }
  return bridge.getCoreBaseUrl();
}

export function subscribeCoreRuntimeState(
  callback: (state: CoreRuntimeState) => void
): (() => void) | null {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.onCoreRuntimeState) {
    return null;
  }
  return bridge.onCoreRuntimeState(callback);
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
