import { contextBridge, ipcRenderer } from "electron";

interface OpenDirectoryDialogResult {
  canceled: boolean;
  filePaths: string[];
}

export interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
}

const electronBridge = {
  version: process.versions.electron,
  async showOpenDirectory(): Promise<string | null> {
    const result = (await ipcRenderer.invoke(
      "dialog:open-directory"
    )) as OpenDirectoryDialogResult | null;
    if (!result || result.canceled || result.filePaths.length === 0) {
      return null;
    }
    return result.filePaths[0] ?? null;
  },
  async openExternalUrl(url: string): Promise<void> {
    await ipcRenderer.invoke("auth:open-external-url", url);
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
