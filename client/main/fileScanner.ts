import fs from "node:fs/promises";
import path from "node:path";

import { dialog, ipcMain } from "electron";

// 桌面端媒体选择器当前接受的视频格式。
const VIDEO_EXTENSIONS = new Set([".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"]);

// Main Process 返回给 Renderer 的本地视频文件引用。
export interface DesktopMediaFileReference {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
}

// 媒体选择/扫描 IPC 的统一返回结构。
export interface OpenDirectoryScanResult {
  canceled: boolean;
  folderPath: string | null;
  files: DesktopMediaFileReference[];
}

// 根据视频扩展名推导 MIME type，供后续播放/导入使用。
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

// 将一个绝对路径转换成 Renderer/Core 可消费的媒体文件引用。
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

// 将 Windows WSL UNC 路径转换为 core 可访问的 Linux 路径。
function normalizePathForLocalCore(nativePath: string): string {
  const wslMatch = nativePath.match(/^\\\\wsl(?:\.localhost|\$)\\[^\\]+\\(.+)$/i);
  if (!wslMatch) {
    return nativePath;
  }
  return `/${wslMatch[1]!.replaceAll("\\", "/")}`;
}

// 兼容 Windows 反斜杠路径的 basename 提取。
function basenameForNativePath(nativePath: string): string {
  return path.basename(nativePath.replaceAll("\\", "/"));
}

// 在多种路径表示中找到第一个真实存在的文件。
async function statFirstExistingFile(paths: string[]): Promise<{ isFile: () => boolean; size: number } | null> {
  for (const candidate of paths) {
    try {
      const stat = await fs.stat(candidate);
      if (stat.isFile()) {
        return stat;
      }
    } catch {
      // Windows UNC 和 WSL 路径不能互换，失败后继续尝试下一种表示。
    }
  }
  return null;
}

// 递归扫描目录，收集其中所有支持的视频文件。
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

// 汇总用户选择的文件/目录；文件直接校验，目录递归扫描。
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

// 注册媒体选择 IPC；Renderer 只通过 dialog:open-media 获取本地视频引用。
export function registerFileScannerIpcHandlers(): void {
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
