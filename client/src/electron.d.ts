export {};

interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
}

interface DesktopMediaFileReference {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
}

type CoreRuntimeStatus = "idle" | "starting" | "ready" | "failed" | "stopped";

interface CoreRuntimeState {
  status: CoreRuntimeStatus;
  baseUrl: string | null;
  pid: number | null;
  lastError: string | null;
}

interface OpenDirectoryResult {
  folderPath: string | null;
  files: DesktopMediaFileReference[];
}

declare global {
  interface Window {
    electron?: {
      version?: string;
      showOpenDirectory?: () => Promise<OpenDirectoryResult | null>;
      openExternalUrl?: (url: string) => Promise<void>;
      getSecureCredential?: (key: string) => Promise<string | null>;
      setSecureCredential?: (key: string, value: string) => Promise<void>;
      deleteSecureCredential?: (key: string) => Promise<void>;
      getCoreBaseUrl?: () => Promise<string | null>;
      getCoreRuntimeState?: () => Promise<CoreRuntimeState>;
      onCoreRuntimeState?: (callback: (state: CoreRuntimeState) => void) => () => void;
      onAuthDeepLink?: (callback: (payload: AuthDeepLinkPayload) => void) => () => void;
    };
  }
}
