import { contextBridge, ipcRenderer } from "electron";

interface OpenDirectoryDialogResult {
  canceled: boolean;
  filePaths: string[];
}

export interface DesktopMediaFileReference {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
}

export interface OpenDirectoryScanResult {
  canceled: boolean;
  folderPath: string | null;
  files: DesktopMediaFileReference[];
}

export interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
}

const electronBridge = {
  version: process.versions.electron,
  async showOpenDirectory(): Promise<OpenDirectoryScanResult | null> {
    const result = (await ipcRenderer.invoke(
      "dialog:open-directory"
    )) as OpenDirectoryDialogResult | OpenDirectoryScanResult | null;
    if (!result || result.canceled) {
      return null;
    }
    if ("files" in result) {
      return result;
    }
    const folderPath = result.filePaths[0] ?? null;
    return {
      canceled: false,
      folderPath,
      files: [],
    };
  },
  async openExternalUrl(url: string): Promise<void> {
    await ipcRenderer.invoke("auth:open-external-url", url);
  },
  async getSecureCredential(key: string): Promise<string | null> {
    return (await ipcRenderer.invoke("secure-store:get", key)) as string | null;
  },
  async setSecureCredential(key: string, value: string): Promise<void> {
    await ipcRenderer.invoke("secure-store:set", key, value);
  },
  async deleteSecureCredential(key: string): Promise<void> {
    await ipcRenderer.invoke("secure-store:delete", key);
  },
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

contextBridge.exposeInMainWorld("electron", electronBridge);
