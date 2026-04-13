export {};

interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
}

type CoreRuntimeStatus = "idle" | "starting" | "ready" | "failed" | "stopped";

interface CoreRuntimeState {
  status: CoreRuntimeStatus;
  baseUrl: string | null;
  pid: number | null;
  lastError: string | null;
}

declare global {
  type OpenDirectoryResult = string | null;

  interface Window {
    electron?: {
      version?: string;
      showOpenDirectory?: () => Promise<OpenDirectoryResult>;
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
