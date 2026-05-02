import { contextBridge, ipcRenderer, webUtils } from "electron";

// Renderer 可安全持有的桌面媒体文件引用。
export interface DesktopMediaFileReference {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
}

// Main Process 扫描媒体后的统一返回结构。
export interface OpenDirectoryScanResult {
  canceled: boolean;
  folderPath: string | null;
  files: DesktopMediaFileReference[];
}

// 本地媒体注册后的可播放 URL 信息。
export interface LocalMediaRegistration {
  name: string;
  path: string;
  url: string;
  mime_type?: string;
}

// 登录 deep link 派发给 Renderer 的最小载荷。
export interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
}

export type CoreRuntimeStatus = "idle" | "starting" | "ready" | "failed" | "stopped";

// Main Process 托管 core 的运行态快照。
export interface CoreRuntimeState {
  status: CoreRuntimeStatus;
  baseUrl: string | null;
  pid: number | null;
  lastError: string | null;
}

// 暴露给 Renderer 的受控桌面能力集合。
const electronBridge = {
  // Electron 版本号，用于 Renderer 判断 bridge 是否存在。
  version: process.versions.electron,

  // 打开媒体选择框；文件直接返回路径，目录会递归扫描视频文件。
  async showOpenMedia(): Promise<OpenDirectoryScanResult | null> {
    const result = (await ipcRenderer.invoke("dialog:open-media")) as OpenDirectoryScanResult | null;
    if (!result || result.canceled) {
      return null;
    }
    return result;
  },

  // 从浏览器 File 对象取出真实本地路径；普通网页环境不可用。
  getPathForFile(file: File): string | null {
    const filePath = webUtils.getPathForFile(file);
    return filePath.trim().length > 0 ? filePath : null;
  },

  // 把本地媒体文件注册为 entrocut-media:// 可播放 URL。
  async registerLocalMediaFiles(files: DesktopMediaFileReference[]): Promise<LocalMediaRegistration[]> {
    return (await ipcRenderer.invoke("local-media:register", files)) as LocalMediaRegistration[];
  },

  // 请求 Main Process 用系统浏览器打开外部 URL。
  async openExternalUrl(url: string): Promise<void> {
    await ipcRenderer.invoke("auth:open-external-url", url);
  },

  // 从 Main Process 的安全存储读取 credential。
  async getSecureCredential(key: string): Promise<string | null> {
    return (await ipcRenderer.invoke("secure-store:get", key)) as string | null;
  },

  // 写入 Main Process 的安全 credential 存储。
  async setSecureCredential(key: string, value: string): Promise<void> {
    await ipcRenderer.invoke("secure-store:set", key, value);
  },

  // 删除 Main Process 中指定 credential。
  async deleteSecureCredential(key: string): Promise<void> {
    await ipcRenderer.invoke("secure-store:delete", key);
  },

  // 获取当前 core API base URL。
  async getCoreBaseUrl(): Promise<string | null> {
    return (await ipcRenderer.invoke("core:get-base-url")) as string | null;
  },

  // 获取当前 core 托管运行态。
  async getCoreRuntimeState(): Promise<CoreRuntimeState> {
    return (await ipcRenderer.invoke("core:get-runtime-state")) as CoreRuntimeState;
  },

  // 订阅 core 运行态推送；返回值用于取消订阅。
  onCoreRuntimeState(callback: (state: CoreRuntimeState) => void): () => void {
    const listener = (_event: Electron.IpcRendererEvent, state: CoreRuntimeState) => {
      callback(state);
    };
    ipcRenderer.on("core:runtime-state", listener);
    return () => {
      ipcRenderer.removeListener("core:runtime-state", listener);
    };
  },

  // 订阅桌面登录 deep link；返回值用于取消订阅。
  onAuthDeepLink(callback: (payload: AuthDeepLinkPayload) => void): () => void {
    const listener = (_event: Electron.IpcRendererEvent, payload: AuthDeepLinkPayload) => {
      callback(payload);
    };
    ipcRenderer.on("auth:deep-link", listener);
    return () => {
      ipcRenderer.removeListener("auth:deep-link", listener);
    };
  },
};

console.log("[preload] loaded", process.versions.electron);
// 只暴露 electronBridge，不把 Node.js/Electron 原始 API 泄露给 Renderer。
contextBridge.exposeInMainWorld("electron", electronBridge);
