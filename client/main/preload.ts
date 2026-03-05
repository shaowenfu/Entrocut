import { contextBridge, ipcRenderer } from "electron";

interface OpenDirectoryDialogResult {
  canceled: boolean;
  filePaths: string[];
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
};

contextBridge.exposeInMainWorld("electron", electronBridge);
