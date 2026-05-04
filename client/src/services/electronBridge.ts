// 媒体选择输入：可来自目录，也可来自文件列表。
export interface MediaPickInput {
  folderPath?: string;
  files?: Array<File | DesktopMediaFileReference>;
}

// 媒体选择输出：归一化后的目录或文件列表。
export interface MediaPickResult {
  folderPath?: string;
  files?: Array<File | DesktopMediaFileReference>;
}

// Electron main 返回的本地媒体文件引用。
export interface DesktopMediaFileReference {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
}

// 本地媒体协议注册结果。
export interface LocalMediaRegistration {
  name: string;
  path: string;
  url: string;
  mime_type?: string;
}

// Electron deep link 登录回调载荷。
export interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
}

// 本地 core 生命周期状态。
export type CoreRuntimeStatus = "idle" | "starting" | "ready" | "failed" | "stopped";

// Electron main 上报的 core 运行状态。
export interface CoreRuntimeState {
  status: CoreRuntimeStatus;
  baseUrl: string | null;
  pid: number | null;
  lastError: string | null;
}

// 媒体选择模式：强制 Electron、强制浏览器文件、或自动。
export type MediaPickMode = "electron-media" | "browser-files" | "auto";

// 判断文件列表是否非空。
function hasValidFiles(files?: Array<File | DesktopMediaFileReference>): files is Array<File | DesktopMediaFileReference> {
  return Array.isArray(files) && files.length > 0;
}

// 判断是否是桌面端可信本地文件引用。
function isDesktopMediaFileReference(file: File | DesktopMediaFileReference): file is DesktopMediaFileReference {
  return "path" in file && typeof file.path === "string";
}

// 判断 preload bridge 是否可用。
export function isElectronEnvironment(): boolean {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  return Boolean(
    bridge?.showOpenMedia ||
    bridge?.getPathForFile ||
    bridge?.version
  );
}

// 通过 userAgent 粗略判断是否运行在 Electron 外壳内。
export function isLikelyElectronShell(): boolean {
  if (typeof navigator === "undefined") {
    return false;
  }
  return navigator.userAgent.toLowerCase().includes("electron");
}

// 归一化媒体输入，过滤空文件并补齐桌面文件路径。
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

// 调用 Electron 原生媒体选择框。
export async function pickMediaFromElectron(): Promise<MediaPickResult | null> {
  const bridge = window.electron;
  if (!bridge?.showOpenMedia) {
    return null;
  }
  const picked = await bridge.showOpenMedia();
  if (!picked || picked.files.length === 0) {
    return null;
  }
  return { files: picked.files };
}

// 浏览器 fallback：用隐藏 input 选择视频文件。
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

    // 清理临时 input 和取消检测计时器。
    const cleanup = () => {
      if (cancelTimer !== null) {
        window.clearTimeout(cancelTimer);
        cancelTimer = null;
      }
      input.value = "";
      window.removeEventListener("focus", handleWindowFocus, true);
      input.remove();
    };

    // 文件对话框关闭后，若没有 onchange，则视为取消。
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

// 从 File 读取真实本地路径，并转换 WSL 路径给本地 core 使用。
export function getPathForFile(file: File): string | null {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  const filePath =
    bridge?.getPathForFile?.(file) ??
    (file as File & { path?: string }).path ??
    "";
  const normalized = normalizePathForLocalCore(filePath.trim());
  return normalized.length > 0 ? normalized : null;
}

// 把 Windows WSL UNC 路径转换成本地 Linux 路径。
export function normalizePathForLocalCore(nativePath: string): string {
  const wslMatch = nativePath.match(/^\\\\wsl(?:\.localhost|\$)\\[^\\]+\\(.+)$/i);
  if (!wslMatch) {
    return nativePath;
  }
  return `/${wslMatch[1]!.replaceAll("\\", "/")}`;
}

// 把浏览器 File 转成桌面端媒体引用。
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

// 批量转换 File 列表为桌面端媒体引用。
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

// 按当前运行环境选择媒体：Electron 优先，浏览器 fallback。
export async function pickMediaFromSystem(): Promise<MediaPickResult | null> {
  if (isElectronEnvironment()) {
    return pickMediaFromElectron();
  }
  const files = await pickVideoFilesFromBrowser();
  if (!files || files.length === 0) {
    return null;
  }
  return { files };
}

// 按指定模式选择媒体。
export async function pickMediaByMode(mode: MediaPickMode): Promise<MediaPickResult | null> {
  if (mode === "electron-media") {
    return pickMediaFromElectron();
  }
  if (mode === "browser-files") {
    const files = await pickVideoFilesFromBrowser();
    return files && files.length > 0 ? { files } : null;
  }
  // auto 模式：保持 Electron 优先、浏览器 fallback 的逻辑。
  return pickMediaFromSystem();
}

// 把本地媒体文件注册为 Renderer 可访问的协议 URL。
export async function registerLocalMediaFiles(
  files: DesktopMediaFileReference[]
): Promise<LocalMediaRegistration[]> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.registerLocalMediaFiles) {
    return [];
  }
  return bridge.registerLocalMediaFiles(files);
}

// 打开外部链接：桌面端走 shell，浏览器端走 window.open。
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

// 从 Electron secure store 读取凭据。
export async function getSecureCredential(key: string): Promise<string | null> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.getSecureCredential) {
    return null;
  }
  return bridge.getSecureCredential(key);
}

// 写入 Electron secure store 凭据。
export async function setSecureCredential(key: string, value: string): Promise<void> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.setSecureCredential) {
    return;
  }
  await bridge.setSecureCredential(key, value);
}

// 删除 Electron secure store 凭据。
export async function deleteSecureCredential(key: string): Promise<void> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.deleteSecureCredential) {
    return;
  }
  await bridge.deleteSecureCredential(key);
}


// 获取 Electron main 中的 core 运行状态。
export async function getCoreRuntimeState(): Promise<CoreRuntimeState | null> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.getCoreRuntimeState) {
    return null;
  }
  return bridge.getCoreRuntimeState();
}

// 获取 Electron main 分配的 core base URL。
export async function getCoreBaseUrlFromElectron(): Promise<string | null> {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.getCoreBaseUrl) {
    return null;
  }
  return bridge.getCoreBaseUrl();
}

// 订阅 core 运行状态变化。
export function subscribeCoreRuntimeState(
  callback: (state: CoreRuntimeState) => void
): (() => void) | null {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.onCoreRuntimeState) {
    return null;
  }
  return bridge.onCoreRuntimeState(callback);
}
// 订阅 Electron deep link 登录事件。
export function subscribeAuthDeepLink(
  callback: (payload: AuthDeepLinkPayload) => void
): (() => void) | null {
  const bridge = typeof window !== "undefined" ? window.electron : undefined;
  if (!bridge?.onAuthDeepLink) {
    return null;
  }
  return bridge.onAuthDeepLink(callback);
}
