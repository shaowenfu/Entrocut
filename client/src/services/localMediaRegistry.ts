import {
  registerLocalMediaFiles,
  type DesktopMediaFileReference,
} from "./electronBridge";

interface LocalMediaSource {
  assetName: string;
  url: string;
  mimeType: string | null;
  kind: "object_url" | "local_media_url";
}

const projectMediaRegistry = new Map<string, Map<string, LocalMediaSource>>();

function normalizeAssetName(assetName: string): string {
  return assetName.trim().toLowerCase();
}

function ensureProjectRegistry(projectId: string): Map<string, LocalMediaSource> {
  const existing = projectMediaRegistry.get(projectId);
  if (existing) {
    return existing;
  }
  const created = new Map<string, LocalMediaSource>();
  projectMediaRegistry.set(projectId, created);
  return created;
}

function isDesktopFileReference(file: File | DesktopMediaFileReference): file is DesktopMediaFileReference {
  return "path" in file && typeof file.path === "string";
}

function normalizeMediaPathKey(filePath: string): string {
  return filePath.trim();
}

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

export function getProjectMediaSource(projectId: string, assetName: string): LocalMediaSource | null {
  const projectRegistry = projectMediaRegistry.get(projectId);
  if (!projectRegistry) {
    return null;
  }
  return projectRegistry.get(normalizeAssetName(assetName)) ?? null;
}

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

    const cleanup = () => {
      video.pause();
      video.removeAttribute("src");
      video.load();
    };

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
