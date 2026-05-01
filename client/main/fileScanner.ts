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

function mimeTypeForVideoPath(filePath: string): string | undefined {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".mp4" || ext === ".m4v") {
    return "video/mp4";
  }
  if (ext === ".mov") {
    return "video/quicktime";
  }
  if (ext === ".webm") {
    return "video/webm";
  }
  if (ext === ".mkv") {
    return "video/x-matroska";
  }
  if (ext === ".avi") {
    return "video/x-msvideo";
  }
  return undefined;
}

async function toDesktopMediaFileReference(absolutePath: string): Promise<DesktopMediaFileReference | null> {
  const corePath = normalizePathForLocalCore(absolutePath);
  const ext = path.extname(corePath).toLowerCase();
  if (!VIDEO_EXTENSIONS.has(ext)) {
    return null;
  }
  const stat = await statFirstExistingFile([corePath, absolutePath]);
  if (stat === null && corePath === absolutePath) {
    return null;
  }
  return {
    name: basenameForNativePath(corePath),
    path: corePath,
    size_bytes: stat?.size,
    mime_type: mimeTypeForVideoPath(corePath),
  };
}

function normalizePathForLocalCore(nativePath: string): string {
  const wslMatch = nativePath.match(/^\\\\wsl(?:\.localhost|\$)\\[^\\]+\\(.+)$/i);
  if (!wslMatch) {
    return nativePath;
  }
  return `/${wslMatch[1]!.replaceAll("\\", "/")}`;
}

function basenameForNativePath(nativePath: string): string {
  return path.basename(nativePath.replaceAll("\\", "/"));
}

async function statFirstExistingFile(paths: string[]): Promise<{ isFile: () => boolean; size: number } | null> {
  for (const candidate of paths) {
    try {
      const stat = await fs.stat(candidate);
      if (stat.isFile()) {
        return stat;
      }
    } catch {
      // Try the next path representation; Windows UNC and WSL paths are not interchangeable.
    }
  }
  return null;
}

async function scanVideoFiles(folderPath: string): Promise<DesktopMediaFileReference[]> {
  const scanPath = normalizePathForLocalCore(folderPath);
  const files: DesktopMediaFileReference[] = [];
  const pendingDirectories = [scanPath];
  while (pendingDirectories.length > 0) {
    const currentDirectory = pendingDirectories.pop();
    if (!currentDirectory) {
      continue;
    }
    let entries;
    try {
      entries = await fs.readdir(currentDirectory, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const absolutePath = path.join(currentDirectory, entry.name);
      if (entry.isDirectory()) {
        pendingDirectories.push(absolutePath);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      const fileRef = await toDesktopMediaFileReference(absolutePath);
      if (fileRef) {
        files.push(fileRef);
      }
    }
  }
  return files;
}

async function collectMediaFromPaths(filePaths: string[]): Promise<DesktopMediaFileReference[]> {
  const files: DesktopMediaFileReference[] = [];
  for (const filePath of filePaths) {
    const normalizedPath = normalizePathForLocalCore(filePath);
    let stat;
    try {
      stat = await fs.stat(normalizedPath);
    } catch {
      continue;
    }
    if (stat.isDirectory()) {
      files.push(...await scanVideoFiles(normalizedPath));
      continue;
    }
    if (stat.isFile()) {
      const fileRef = await toDesktopMediaFileReference(normalizedPath);
      if (fileRef) {
        files.push(fileRef);
      }
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
    const files = await scanVideoFiles(folderPath);
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

  ipcMain.handle("dialog:open-media", async (): Promise<OpenDirectoryScanResult> => {
    const result = await dialog.showOpenDialog({
      title: "Select Video Files or Media Folders",
      properties: ["openFile", "openDirectory", "multiSelections"],
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
    return {
      canceled: false,
      folderPath: null,
      files: await collectMediaFromPaths(result.filePaths),
    };
  });
}
