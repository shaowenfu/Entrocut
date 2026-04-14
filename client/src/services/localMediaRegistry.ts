interface LocalMediaSource {
  assetName: string;
  url: string;
  mimeType: string | null;
  kind: "object_url" | "file_url";
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

function toFileUrl(path: string): string {
  if (path.startsWith("file://")) {
    return path;
  }
  return `file://${encodeURI(path)}`;
}

export function registerProjectMediaSources(
  projectId: string,
  input?: {
    folderPath?: string;
    files?: Array<File | { name: string; path: string; mime_type?: string }>;
  } | null
): void {
  if (!input) {
    return;
  }

  const projectRegistry = ensureProjectRegistry(projectId);
  const files = input.files ?? [];
  for (const file of files) {
    const isDesktopFile = "path" in file && typeof file.path === "string";
    const filePath = isDesktopFile ? file.path.trim() : ((file as File & { path?: string }).path ?? "").trim();
    const existing = projectRegistry.get(normalizeAssetName(file.name));
    if (existing?.kind === "object_url") {
      URL.revokeObjectURL(existing.url);
    }
    const mimeType = isDesktopFile ? (file.mime_type ?? null) : ((file as File).type || null);
    projectRegistry.set(normalizeAssetName(file.name), {
      assetName: file.name,
      url: filePath ? toFileUrl(filePath) : URL.createObjectURL(file as File),
      mimeType,
      kind: filePath ? "file_url" : "object_url",
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
