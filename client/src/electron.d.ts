export {};

declare global {
  interface Window {
    electron?: {
      version?: string;
    };
  }
}
