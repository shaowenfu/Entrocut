import { createReadStream } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";

import { ipcMain, protocol } from "electron";

const LOCAL_MEDIA_PROTOCOL = "entrocut-media";
const VIDEO_EXTENSIONS = new Set([".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"]);

interface DesktopMediaFileReference {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
}

interface LocalMediaRegistration {
  name: string;
  path: string;
  url: string;
  mime_type?: string;
}

interface RegisteredLocalMedia {
  path: string;
  mimeType?: string;
}

const registeredMedia = new Map<string, RegisteredLocalMedia>();

export function registerLocalMediaProtocolScheme(): void {
  protocol.registerSchemesAsPrivileged([
    {
      scheme: LOCAL_MEDIA_PROTOCOL,
      privileges: {
        standard: true,
        secure: true,
        supportFetchAPI: true,
        stream: true,
      },
    },
  ]);
}

function normalizePathForLocalCore(nativePath: string): string {
  const wslMatch = nativePath.match(/^\\\\wsl(?:\.localhost|\$)\\[^\\]+\\(.+)$/i);
  if (!wslMatch) {
    return nativePath;
  }
  return `/${wslMatch[1]!.replaceAll("\\", "/")}`;
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

function createMediaToken(filePath: string): string {
  const randomPart = Math.random().toString(36).slice(2, 12);
  return `${Date.now().toString(36)}_${randomPart}_${Buffer.from(filePath).toString("base64url").slice(0, 12)}`;
}

function localMediaUrl(token: string, fileName: string): string {
  return `${LOCAL_MEDIA_PROTOCOL}://media/${encodeURIComponent(token)}/${encodeURIComponent(fileName)}`;
}

function parseRangeHeader(rangeHeader: string | null, size: number): { start: number; end: number } | null {
  if (!rangeHeader) {
    return null;
  }
  const match = rangeHeader.match(/^bytes=(\d*)-(\d*)$/);
  if (!match) {
    return null;
  }
  const startText = match[1] ?? "";
  const endText = match[2] ?? "";
  if (!startText && !endText) {
    return null;
  }
  if (!startText) {
    const suffixLength = Number.parseInt(endText, 10);
    if (!Number.isFinite(suffixLength) || suffixLength <= 0) {
      return null;
    }
    return {
      start: Math.max(0, size - suffixLength),
      end: size - 1,
    };
  }
  const start = Number.parseInt(startText, 10);
  const end = endText ? Number.parseInt(endText, 10) : size - 1;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start || start >= size) {
    return null;
  }
  return {
    start,
    end: Math.min(end, size - 1),
  };
}

function streamResponse(filePath: string, options: {
  status: number;
  start: number;
  end: number;
  size: number;
  mimeType?: string;
}): Response {
  const headers = new Headers({
    "accept-ranges": "bytes",
    "access-control-allow-origin": "*",
    "content-length": String(options.end - options.start + 1),
  });
  if (options.status === 206) {
    headers.set("content-range", `bytes ${options.start}-${options.end}/${options.size}`);
  }
  if (options.mimeType) {
    headers.set("content-type", options.mimeType);
  }
  return new Response(Readable.toWeb(createReadStream(filePath, {
    start: options.start,
    end: options.end,
  })) as ReadableStream, {
    status: options.status,
    headers,
  });
}

async function registerLocalMediaFile(file: DesktopMediaFileReference): Promise<LocalMediaRegistration | null> {
  const filePath = normalizePathForLocalCore(file.path.trim());
  if (!path.isAbsolute(filePath)) {
    return null;
  }
  if (!VIDEO_EXTENSIONS.has(path.extname(filePath).toLowerCase())) {
    return null;
  }

  const stat = await fs.stat(filePath);
  if (!stat.isFile()) {
    return null;
  }

  const token = createMediaToken(filePath);
  const mimeType = file.mime_type ?? mimeTypeForVideoPath(filePath);
  registeredMedia.set(token, {
    path: filePath,
    mimeType,
  });

  return {
    name: file.name,
    path: filePath,
    url: localMediaUrl(token, path.basename(filePath)),
    mime_type: mimeType,
  };
}

export function registerLocalMediaProtocolHandlers(): void {
  protocol.handle(LOCAL_MEDIA_PROTOCOL, async (request) => {
    const parsed = new URL(request.url);
    if (parsed.hostname !== "media") {
      return new Response("not_found", { status: 404 });
    }

    const token = decodeURIComponent(parsed.pathname.split("/").filter(Boolean)[0] ?? "");
    const media = registeredMedia.get(token);
    if (!media) {
      return new Response("not_found", { status: 404 });
    }

    const stat = await fs.stat(media.path);
    if (!stat.isFile()) {
      return new Response("not_found", { status: 404 });
    }

    const size = stat.size;
    if (size <= 0) {
      return new Response("not_found", { status: 404 });
    }
    const range = parseRangeHeader(request.headers.get("range"), size);
    if (request.headers.has("range") && !range) {
      return new Response("range_not_satisfiable", {
        status: 416,
        headers: {
          "content-range": `bytes */${size}`,
          "access-control-allow-origin": "*",
        },
      });
    }

    return streamResponse(media.path, {
      status: range ? 206 : 200,
      start: range?.start ?? 0,
      end: range?.end ?? Math.max(0, size - 1),
      size,
      mimeType: media.mimeType,
    });
  });

  ipcMain.handle("local-media:register", async (_event, files: DesktopMediaFileReference[]) => {
    if (!Array.isArray(files)) {
      return [];
    }
    const registrations: LocalMediaRegistration[] = [];
    for (const file of files) {
      if (!file || typeof file.path !== "string" || typeof file.name !== "string") {
        continue;
      }
      try {
        const registration = await registerLocalMediaFile(file);
        if (registration) {
          registrations.push(registration);
        }
      } catch {
        // Invalid or inaccessible files are ignored; core import validation remains the source of truth.
      }
    }
    return registrations;
  });
}
