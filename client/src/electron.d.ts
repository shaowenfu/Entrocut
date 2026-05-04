export {};

// Electron deep link 登录回调载荷。
interface AuthDeepLinkPayload {
  // 后端登录会话 id，用于兑换本地登录态。
  loginSessionId: string;
  // 当前只接受已认证完成的回调。
  status: "authenticated";
}

// Electron main 返回给 Renderer 的本地媒体文件引用。
interface DesktopMediaFileReference {
  // 展示用文件名。
  name: string;
  // 本机绝对路径，只能来自桌面端可信选择流程。
  path: string;
  // 文件大小，单位 byte。
  size_bytes?: number;
  // MIME 类型，用于前端预览和 core 识别。
  mime_type?: string;
}

// 本地 core 进程生命周期状态。
type CoreRuntimeStatus = "idle" | "starting" | "ready" | "failed" | "stopped";

// Electron main 管理的 core 运行状态快照。
interface CoreRuntimeState {
  // 当前 core 生命周期状态。
  status: CoreRuntimeStatus;
  // core HTTP 服务地址，ready 后应存在。
  baseUrl: string | null;
  // core 子进程 pid，仅桌面端存在。
  pid: number | null;
  // 最近一次启动/运行错误。
  lastError: string | null;
}

// 媒体选择结果：可来自单个/多个视频文件，也可来自目录扫描。
interface OpenDirectoryResult {
  // 用户选择目录时的目录路径；选择文件时通常为空。
  folderPath: string | null;
  // 最终可导入的视频文件列表。
  files: DesktopMediaFileReference[];
}

// 注册到本地媒体协议后的媒体引用。
interface LocalMediaRegistration {
  // 展示用文件名。
  name: string;
  // 本机绝对路径。
  path: string;
  // Renderer 可安全访问的 local media URL。
  url: string;
  // MIME 类型，用于 video/image 等元素选择解码方式。
  mime_type?: string;
}

declare global {
  interface Window {
    // preload 暴露的桌面能力桥；浏览器模式下可能不存在。
    electron?: {
      // 桌面 bridge 版本标识。
      version?: string;
      // 打开媒体选择框，返回视频文件或目录扫描结果。
      showOpenMedia?: () => Promise<OpenDirectoryResult | null>;
      // 从 File 对象读取 Electron 注入的真实本地路径。
      getPathForFile?: (file: File) => string | null;
      // 把本地文件注册为 Renderer 可访问的协议 URL。
      registerLocalMediaFiles?: (files: DesktopMediaFileReference[]) => Promise<LocalMediaRegistration[]>;
      // 用系统默认浏览器打开外部链接。
      openExternalUrl?: (url: string) => Promise<void>;
      // 从安全存储读取凭据。
      getSecureCredential?: (key: string) => Promise<string | null>;
      // 写入安全存储凭据。
      setSecureCredential?: (key: string, value: string) => Promise<void>;
      // 删除安全存储凭据。
      deleteSecureCredential?: (key: string) => Promise<void>;
      // 获取当前 core HTTP base URL。
      getCoreBaseUrl?: () => Promise<string | null>;
      // 获取 core 运行状态快照。
      getCoreRuntimeState?: () => Promise<CoreRuntimeState>;
      // 订阅 core 运行状态变化，返回取消订阅函数。
      onCoreRuntimeState?: (callback: (state: CoreRuntimeState) => void) => () => void;
      // 订阅 Electron deep link 登录事件，返回取消订阅函数。
      onAuthDeepLink?: (callback: (payload: AuthDeepLinkPayload) => void) => () => void;
    };
  }
}
