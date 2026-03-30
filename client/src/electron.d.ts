export {};

interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
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
      onAuthDeepLink?: (callback: (payload: AuthDeepLinkPayload) => void) => () => void;
    };
  }
}
