import fs from "node:fs/promises";
import path from "node:path";

import { dialog, ipcMain } from "electron";

const VIDEO_EXTENSIONS = new Set([".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"]);

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

async function toDesktopMediaFileReference(absolutePath: string): Promise<DesktopMediaFileReference | null> {
  const stat = await fs.stat(absolutePath);
  if (!stat.isFile()) {
    return null;
  }
  const ext = path.extname(absolutePath).toLowerCase();
  if (!VIDEO_EXTENSIONS.has(ext)) {
    return null;
  }
  return {
    name: path.basename(absolutePath),
    path: absolutePath,
    size_bytes: stat.size,
    mime_type: undefined,
  };
}

async function scanTopLevelVideoFiles(folderPath: string): Promise<DesktopMediaFileReference[]> {
  const entries = await fs.readdir(folderPath, { withFileTypes: true });
  const files: DesktopMediaFileReference[] = [];
  for (const entry of entries) {
    if (!entry.isFile()) {
      continue;
    }
    const ext = path.extname(entry.name).toLowerCase();
    if (!VIDEO_EXTENSIONS.has(ext)) {
      continue;
    }
    const absolutePath = path.join(folderPath, entry.name);
    const fileRef = await toDesktopMediaFileReference(absolutePath);
    if (fileRef) {
      files.push(fileRef);
    }
  }
  return files;
}

export function registerFileScannerIpcHandlers(): void {
  ipcMain.handle("dialog:open-directory", async (): Promise<OpenDirectoryScanResult> => {
    const result = await dialog.showOpenDialog({
      title: "Select Media Folder",
      properties: ["openDirectory"],
    });
    if (result.canceled || result.filePaths.length === 0) {
      return { canceled: true, folderPath: null, files: [] };
    }
    const folderPath = result.filePaths[0] ?? null;
    if (!folderPath) {
      return { canceled: true, folderPath: null, files: [] };
    }
    const files = await scanTopLevelVideoFiles(folderPath);
    return {
      canceled: false,
      folderPath,
      files,
    };
  });

  ipcMain.handle("dialog:open-videos", async (): Promise<OpenDirectoryScanResult> => {
    const result = await dialog.showOpenDialog({
      title: "Select Videos",
      properties: ["openFile", "multiSelections"],
      filters: [
        {
          name: "Video Files",
          extensions: ["mp4", "mov", "m4v", "webm", "mkv", "avi"],
        },
      ],
    });
    if (result.canceled || result.filePaths.length === 0) {
      return { canceled: true, folderPath: null, files: [] };
    }
    const files = (
      await Promise.all(result.filePaths.map((filePath) => toDesktopMediaFileReference(filePath)))
    ).filter((file): file is DesktopMediaFileReference => Boolean(file));
    return {
      canceled: false,
      folderPath: null,
      files,
    };
  });
}
