import { contextBridge, ipcRenderer } from "electron";

interface OpenDirectoryDialogResult {
  canceled: boolean;
  filePaths: string[];
}

export interface AuthDeepLinkPayload {
  loginSessionId: string;
  status: "authenticated";
}

export type CoreRuntimeStatus = "idle" | "starting" | "ready" | "failed" | "stopped";

export interface CoreRuntimeState {
  status: CoreRuntimeStatus;
  baseUrl: string | null;
  pid: number | null;
  lastError: string | null;
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
  async getSecureCredential(key: string): Promise<string | null> {
    return (await ipcRenderer.invoke("secure-store:get", key)) as string | null;
  },
  async setSecureCredential(key: string, value: string): Promise<void> {
    await ipcRenderer.invoke("secure-store:set", key, value);
  },
  async deleteSecureCredential(key: string): Promise<void> {
    await ipcRenderer.invoke("secure-store:delete", key);
  },
  async getCoreBaseUrl(): Promise<string | null> {
    return (await ipcRenderer.invoke("core:get-base-url")) as string | null;
  },
  async getCoreRuntimeState(): Promise<CoreRuntimeState> {
    return (await ipcRenderer.invoke("core:get-runtime-state")) as CoreRuntimeState;
  },
  onCoreRuntimeState(callback: (state: CoreRuntimeState) => void): () => void {
    const listener = (_event: Electron.IpcRendererEvent, state: CoreRuntimeState) => {
      callback(state);
    };
    ipcRenderer.on("core:runtime-state", listener);
    return () => {
      ipcRenderer.removeListener("core:runtime-state", listener);
    };
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
