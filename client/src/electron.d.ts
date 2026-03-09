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
      onAuthDeepLink?: (callback: (payload: AuthDeepLinkPayload) => void) => () => void;
    };
  }
}
