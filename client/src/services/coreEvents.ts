export type CoreEventName =
  | "session.ready"
  | "notification"
  | "launchpad.project.initialized"
  | "media.processing.progress"
  | "media.processing.completed"
  | "workspace.chat.received"
  | "workspace.chat.ready"
  | "workspace.patch.ready";

export interface CoreEventEnvelope {
  event: CoreEventName;
  project_id: string;
  session_id?: string | null;
  request_id?: string | null;
  ts: string;
  payload: Record<string, unknown>;
}

type OnEvent = (event: CoreEventEnvelope) => void;
type OnOpen = () => void;
type OnClose = () => void;
type OnError = (event: Event) => void;

const DEFAULT_CORE_WS_BASE_URL = "ws://127.0.0.1:8000";

function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function getCoreWsBaseUrl(): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const fromEnv = env.VITE_CORE_WS_BASE_URL?.trim();
  return trimTrailingSlash(fromEnv && fromEnv.length > 0 ? fromEnv : DEFAULT_CORE_WS_BASE_URL);
}

export function createCoreProjectEventSocket(
  projectId: string,
  handlers: {
    onEvent: OnEvent;
    onOpen?: OnOpen;
    onClose?: OnClose;
    onError?: OnError;
  }
): WebSocket {
  const socket = new WebSocket(`${getCoreWsBaseUrl()}/ws/projects/${projectId}`);

  socket.addEventListener("open", () => {
    handlers.onOpen?.();
  });

  socket.addEventListener("message", (rawEvent) => {
    try {
      const payload = JSON.parse(String(rawEvent.data)) as CoreEventEnvelope;
      if (!payload?.event || !payload?.project_id) {
        return;
      }
      handlers.onEvent(payload);
    } catch {
      // Ignore invalid event payloads in Phase 2 skeleton.
    }
  });

  socket.addEventListener("close", () => {
    handlers.onClose?.();
  });

  socket.addEventListener("error", (event) => {
    handlers.onError?.(event);
  });

  return socket;
}

