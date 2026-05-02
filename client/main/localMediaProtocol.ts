import { createReadStream } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";

import { ipcMain, protocol } from "electron";

// Renderer 中用于播放本地媒体的自定义协议名。
const LOCAL_MEDIA_PROTOCOL = "entrocut-media";
// 桌面端当前允许注册和播放的视频格式。
const VIDEO_EXTENSIONS = new Set([".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"]);

// Renderer 传给 Main Process 的本地媒体文件引用。
interface DesktopMediaFileReference {
  name: string;
  path: string;
  size_bytes?: number;
  mime_type?: string;
}

// Main Process 注册本地媒体后返回给 Renderer 的播放信息。
interface LocalMediaRegistration {
  name: string;
  path: string;
  url: string;
  mime_type?: string;
}

// 协议 token 对应的真实本地文件信息。
interface RegisteredLocalMedia {
  path: string;
  mimeType?: string;
}

// 内存态媒体注册表；token 隔离真实文件路径，不直接暴露给协议 URL。
const registeredMedia = new Map<string, RegisteredLocalMedia>();

// 在 app ready 前注册自定义协议权限，使其支持 fetch 和 stream。
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

// 将 Windows WSL UNC 路径转换为 core 可访问的 Linux 路径。
function normalizePathForLocalCore(nativePath: string): string {
  const wslMatch = nativePath.match(/^\\\\wsl(?:\.localhost|\$)\\[^\\]+\\(.+)$/i);
  if (!wslMatch) {
    return nativePath;
  }
  return `/${wslMatch[1]!.replaceAll("\\", "/")}`;
}

// 根据视频扩展名推导浏览器播放所需 MIME type。
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

// 为本地媒体生成一次性协议 token，避免 URL 直接使用真实路径。
function createMediaToken(filePath: string): string {
  const randomPart = Math.random().toString(36).slice(2, 12);
  return `${Date.now().toString(36)}_${randomPart}_${Buffer.from(filePath).toString("base64url").slice(0, 12)}`;
}

// 生成 Renderer 可交给 video 标签播放的自定义协议 URL。
function localMediaUrl(token: string, fileName: string): string {
  return `${LOCAL_MEDIA_PROTOCOL}://media/${encodeURIComponent(token)}/${encodeURIComponent(fileName)}`;
}

// 解析 HTTP Range header，支持视频拖动和分段读取。
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

// 将本地文件片段包装成协议响应，供 Chromium 流式播放。
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

// 校验并注册单个本地视频文件，返回可播放协议 URL。
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

// 注册自定义协议处理器和 Renderer 调用的本地媒体注册 IPC。
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
        // 无效或不可访问文件在这里只忽略，core import validation 才是事实源。
      }
    }
    return registrations;
  });
}
