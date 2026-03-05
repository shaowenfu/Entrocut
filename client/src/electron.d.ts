export {};

declare global {
  type OpenDirectoryResult = string | null;

  interface Window {
    electron?: {
      version?: string;
      showOpenDirectory?: () => Promise<OpenDirectoryResult>;
    };
  }
}
