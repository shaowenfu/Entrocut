import {
  registerLocalMediaFiles,
  type DesktopMediaFileReference,
} from "./electronBridge";

// Renderer 可播放的本地媒体源。
interface LocalMediaSource {
  assetId?: string;
  assetName: string;
  url: string;
  mimeType: string | null;
  kind: "object_url" | "local_media_url";
}

interface PersistedMediaRegistrationResult {
  registeredAssetIds: string[];
  missingAssetIds: string[];
}

// 按 projectId 隔离的媒体源注册表。
const projectMediaRegistry = new Map<string, Map<string, LocalMediaSource>>();

// 归一化资产名，用于宽松匹配 core asset 和本地文件。
function normalizeAssetName(assetName: string): string {
  return assetName.trim().toLowerCase();
}

function assetIdKey(assetId: string): string {
  return `id:${assetId.trim()}`;
}

// 获取或创建项目级媒体注册表。
function ensureProjectRegistry(projectId: string): Map<string, LocalMediaSource> {
  const existing = projectMediaRegistry.get(projectId);
  if (existing) {
    return existing;
  }
  const created = new Map<string, LocalMediaSource>();
  projectMediaRegistry.set(projectId, created);
  return created;
}

// 判断文件是否是 Electron 桌面文件引用。
function isDesktopFileReference(file: File | DesktopMediaFileReference): file is DesktopMediaFileReference {
  return "path" in file && typeof file.path === "string";
}

// 归一化媒体路径作为 Map key。
function normalizeMediaPathKey(filePath: string): string {
  return filePath.trim();
}

// 注册项目媒体源：桌面文件转 local media URL，浏览器 File 转 object URL。
export async function registerProjectMediaSources(
  projectId: string,
  input?: {
    folderPath?: string;
    files?: Array<File | DesktopMediaFileReference>;
  } | null
): Promise<void> {
  if (!input) {
    return;
  }

  const projectRegistry = ensureProjectRegistry(projectId);
  const files = input.files ?? [];
  const desktopFiles = files.filter(isDesktopFileReference);
  const localMediaByPath = new Map(
    (await registerLocalMediaFiles(desktopFiles)).map((item) => [normalizeMediaPathKey(item.path), item])
  );

  for (const file of files) {
    const existing = projectRegistry.get(normalizeAssetName(file.name));
    if (existing?.kind === "object_url") {
      URL.revokeObjectURL(existing.url);
    }

    if (isDesktopFileReference(file)) {
      const registered = localMediaByPath.get(normalizeMediaPathKey(file.path));
      if (!registered) {
        continue;
      }
      projectRegistry.set(normalizeAssetName(file.name), {
        assetName: file.name,
        url: registered.url,
        mimeType: registered.mime_type ?? file.mime_type ?? null,
        kind: "local_media_url",
      });
      continue;
    }

    projectRegistry.set(normalizeAssetName(file.name), {
      assetName: file.name,
      url: URL.createObjectURL(file),
      mimeType: file.type || null,
      kind: "object_url",
    });
  }
}

// 根据持久化 source_path 重新注册项目素材，供重新打开 Workspace 后继续播放。
export async function registerProjectPersistedMediaSources(
  projectId: string,
  assets: Array<{
    id: string;
    name: string;
    sourcePath?: string | null;
    source_path?: string | null;
    type?: string | null;
  }>
): Promise<PersistedMediaRegistrationResult> {
  const desktopFiles: DesktopMediaFileReference[] = [];
  const expectedAssets = new Map<string, string>();
  for (const asset of assets) {
    const sourcePath = asset.sourcePath ?? asset.source_path ?? null;
    if (!sourcePath || asset.type === "audio") {
      continue;
    }
    expectedAssets.set(asset.id, sourcePath);
    desktopFiles.push({
      name: asset.name,
      path: sourcePath,
    });
  }
  if (desktopFiles.length === 0) {
    return { registeredAssetIds: [], missingAssetIds: [] };
  }

  const projectRegistry = ensureProjectRegistry(projectId);
  const localMediaByPath = new Map(
    (await registerLocalMediaFiles(desktopFiles)).map((item) => [normalizeMediaPathKey(item.path), item])
  );
  const registeredAssetIds: string[] = [];
  const missingAssetIds: string[] = [];
  for (const asset of assets) {
    const sourcePath = asset.sourcePath ?? asset.source_path ?? null;
    if (!sourcePath || asset.type === "audio") {
      continue;
    }
    const registered = localMediaByPath.get(normalizeMediaPathKey(sourcePath));
    if (!registered) {
      projectRegistry.delete(assetIdKey(asset.id));
      projectRegistry.delete(normalizeAssetName(asset.name));
      missingAssetIds.push(asset.id);
      continue;
    }
    const source: LocalMediaSource = {
      assetId: asset.id,
      assetName: asset.name,
      url: registered.url,
      mimeType: registered.mime_type ?? null,
      kind: "local_media_url",
    };
    projectRegistry.set(assetIdKey(asset.id), source);
    projectRegistry.set(normalizeAssetName(asset.name), source);
    registeredAssetIds.push(asset.id);
  }
  for (const assetId of expectedAssets.keys()) {
    if (!registeredAssetIds.includes(assetId) && !missingAssetIds.includes(assetId)) {
      missingAssetIds.push(assetId);
    }
  }
  return { registeredAssetIds, missingAssetIds };
}

// 根据 projectId 和 asset id/name 查找可播放媒体源。
export function getProjectMediaSource(projectId: string, assetIdOrName: string): LocalMediaSource | null {
  const projectRegistry = projectMediaRegistry.get(projectId);
  if (!projectRegistry) {
    return null;
  }
  return projectRegistry.get(assetIdKey(assetIdOrName)) ?? projectRegistry.get(normalizeAssetName(assetIdOrName)) ?? null;
}

// 从视频 URL 抽取一帧生成 JPEG data URL 缩略图。
export async function createThumbnailFromMediaUrl(
  mediaUrl: string,
  options?: {
    seekToSec?: number;
    width?: number;
    height?: number;
  }
): Promise<string | null> {
  if (typeof document === "undefined") {
    return null;
  }

  const seekToSec = options?.seekToSec ?? 0.2;
  const width = options?.width ?? 320;
  const height = options?.height ?? 180;

  return new Promise<string | null>((resolve) => {
    const video = document.createElement("video");
    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;
    video.crossOrigin = "anonymous";

    // 释放 video 元素持有的媒体资源。
    const cleanup = () => {
      video.pause();
      video.removeAttribute("src");
      video.load();
    };

    // 统一失败出口：清理资源并返回 null。
    const fail = () => {
      cleanup();
      resolve(null);
    };

    video.onerror = fail;
    video.onloadedmetadata = () => {
      const targetTime = Number.isFinite(video.duration) ? Math.min(Math.max(0, seekToSec), Math.max(0, video.duration - 0.05)) : seekToSec;
      video.currentTime = targetTime;
    };
    video.onseeked = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d");
        if (!context) {
          fail();
          return;
        }
        context.drawImage(video, 0, 0, width, height);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.78);
        cleanup();
        resolve(dataUrl);
      } catch {
        fail();
      }
    };

    video.src = mediaUrl;
  });
}

// 清理项目媒体源，并释放浏览器 object URL。
export function clearProjectMediaSources(projectId: string): void {
  const projectRegistry = projectMediaRegistry.get(projectId);
  if (!projectRegistry) {
    return;
  }
  for (const source of projectRegistry.values()) {
    if (source.kind === "object_url") {
      URL.revokeObjectURL(source.url);
    }
  }
  projectMediaRegistry.delete(projectId);
}
