import { getAuthToken } from "./httpClient";

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
  event_id?: string;
  sequence?: number;
  session_id?: string | null;
  request_id?: string | null;
  ts: string;
  payload: Record<string, unknown>;
}

type OnEvent = (event: CoreEventEnvelope) => void;
type OnOpen = () => void;
type OnClose = (event: CloseEvent) => void;
type OnError = (event: Event) => void;

export type ReconnectState = "idle" | "reconnecting" | "max_attempts_reached";

interface SocketHandlers {
  onEvent: OnEvent;
  onOpen?: OnOpen;
  onClose?: OnClose;
  onError?: OnError;
  onReconnectStateChange?: (state: ReconnectState) => void;
}

export interface SocketManager {
  socket: WebSocket | null;
  reconnectAttempts: number;
  reconnectState: ReconnectState;
  projectId: string;
  sessionId: string;
  handlers: SocketHandlers;
  closedByClient: boolean;
  heartbeatTimer: number | null;
  reconnectTimer: number | null;
  lastSequence: number;
  getLastSequence?: () => number;
}

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_DELAY_MS = 1000;
const HEARTBEAT_INTERVAL_MS = 30000;
const DEFAULT_CORE_WS_BASE_URL = "ws://127.0.0.1:8000";
const CLIENT_INSTANCE_STORAGE_KEY = "entrocut.client.instance";

function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function getCoreWsBaseUrl(): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const fromEnv = env.VITE_CORE_WS_BASE_URL?.trim();
  return trimTrailingSlash(fromEnv && fromEnv.length > 0 ? fromEnv : DEFAULT_CORE_WS_BASE_URL);
}

function getClientInstanceId(): string {
  if (typeof window === "undefined") {
    return "cli_server";
  }
  const existing = window.localStorage.getItem(CLIENT_INSTANCE_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const generated =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? `cli_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`
      : `cli_${Math.random().toString(16).slice(2, 14)}`;
  window.localStorage.setItem(CLIENT_INSTANCE_STORAGE_KEY, generated);
  return generated;
}

function resolveLastSequence(manager: SocketManager): number {
  const fromGetter = manager.getLastSequence?.();
  if (typeof fromGetter === "number" && Number.isFinite(fromGetter)) {
    return Math.max(manager.lastSequence, Math.floor(fromGetter));
  }
  return Math.max(0, Math.floor(manager.lastSequence));
}

function buildSocketUrl(projectId: string, sessionId: string, lastSequence: number): string {
  const token = getAuthToken();
  const params = new URLSearchParams();
  params.set("session_id", sessionId);
  params.set("client_instance_id", getClientInstanceId());
  params.set("last_sequence", String(lastSequence));
  if (token) {
    params.set("access_token", token);
  }
  return `${getCoreWsBaseUrl()}/ws/projects/${projectId}?${params.toString()}`;
}

function setReconnectState(manager: SocketManager, state: ReconnectState): void {
  manager.reconnectState = state;
  manager.handlers.onReconnectStateChange?.(state);
}

function clearTimers(manager: SocketManager): void {
  if (manager.heartbeatTimer !== null) {
    window.clearInterval(manager.heartbeatTimer);
    manager.heartbeatTimer = null;
  }
  if (manager.reconnectTimer !== null) {
    window.clearTimeout(manager.reconnectTimer);
    manager.reconnectTimer = null;
  }
}

function sendHeartbeat(manager: SocketManager): void {
  if (manager.socket?.readyState === WebSocket.OPEN) {
    manager.socket.send(JSON.stringify({ action: "ping", session_id: manager.sessionId }));
  }
}

function startHeartbeat(manager: SocketManager): void {
  if (manager.heartbeatTimer !== null) {
    return;
  }
  manager.heartbeatTimer = window.setInterval(() => {
    sendHeartbeat(manager);
  }, HEARTBEAT_INTERVAL_MS);
}

function readSequenceFromEvent(payload: CoreEventEnvelope): number | null {
  if (typeof payload.sequence === "number" && Number.isFinite(payload.sequence)) {
    return Math.floor(payload.sequence);
  }
  const lastSequence = payload.payload.last_sequence;
  if (typeof lastSequence === "number" && Number.isFinite(lastSequence)) {
    return Math.floor(lastSequence);
  }
  return null;
}

function scheduleReconnect(manager: SocketManager): void {
  if (manager.closedByClient) {
    return;
  }
  if (manager.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    setReconnectState(manager, "max_attempts_reached");
    manager.handlers.onClose?.(
      new CloseEvent("close", {
        code: 4000,
        reason: "max reconnect attempts reached",
        wasClean: false,
      })
    );
    return;
  }

  manager.reconnectAttempts += 1;
  setReconnectState(manager, "reconnecting");
  const delay = RECONNECT_BASE_DELAY_MS * 2 ** (manager.reconnectAttempts - 1);
  manager.reconnectTimer = window.setTimeout(() => {
    manager.reconnectTimer = null;
    openManagedSocket(manager);
  }, delay);
}

function handleSocketClose(manager: SocketManager, event: CloseEvent): void {
  clearTimers(manager);
  manager.socket = null;

  if (manager.closedByClient) {
    setReconnectState(manager, "idle");
    manager.handlers.onClose?.(event);
    return;
  }

  if (event.code === 4400 || event.code === 4401 || event.code === 4403) {
    setReconnectState(manager, "idle");
    manager.handlers.onClose?.(event);
    return;
  }

  manager.handlers.onClose?.(event);
  scheduleReconnect(manager);
}

function openManagedSocket(manager: SocketManager): void {
  clearTimers(manager);
  const socket = new WebSocket(
    buildSocketUrl(manager.projectId, manager.sessionId, resolveLastSequence(manager))
  );
  manager.socket = socket;

  socket.onopen = () => {
    manager.reconnectAttempts = 0;
    setReconnectState(manager, "idle");
    startHeartbeat(manager);
    manager.handlers.onOpen?.();
  };

  socket.onmessage = (rawEvent: MessageEvent) => {
    try {
      const payload = JSON.parse(String(rawEvent.data)) as CoreEventEnvelope;
      if (!payload?.event || !payload?.project_id) {
        return;
      }
      const nextSequence = readSequenceFromEvent(payload);
      if (nextSequence !== null) {
        manager.lastSequence = Math.max(manager.lastSequence, nextSequence);
      }
      manager.handlers.onEvent(payload);
    } catch {
      // Ignore invalid event payloads.
    }
  };

  socket.onerror = (event: Event) => {
    manager.handlers.onError?.(event);
  };

  socket.onclose = (event: CloseEvent) => {
    handleSocketClose(manager, event);
  };
}

function createEmptyManager(): SocketManager {
  return {
    socket: null,
    reconnectAttempts: 0,
    reconnectState: "idle",
    projectId: "",
    sessionId: "",
    handlers: { onEvent: () => undefined },
    closedByClient: false,
    heartbeatTimer: null,
    reconnectTimer: null,
    lastSequence: 0,
  };
}

export function closeManagedSocket(manager: SocketManager | null): void {
  if (!manager) {
    return;
  }
  manager.closedByClient = true;
  clearTimers(manager);
  const socket = manager.socket;
  manager.socket = null;
  setReconnectState(manager, "idle");
  if (socket && socket.readyState !== WebSocket.CLOSED) {
    socket.close();
  }
}

export function forceReconnect(manager: SocketManager | null): void {
  if (!manager) {
    return;
  }
  manager.closedByClient = false;
  manager.reconnectAttempts = 0;
  clearTimers(manager);
  const socket = manager.socket;
  manager.socket = null;
  if (socket && socket.readyState !== WebSocket.CLOSED) {
    socket.close();
  }
  openManagedSocket(manager);
}

export function getReconnectStateLabel(state: ReconnectState): string {
  switch (state) {
    case "idle":
      return "idle";
    case "reconnecting":
      return "reconnecting";
    case "max_attempts_reached":
      return "max retries";
    default:
      return state;
  }
}

export function createManagedProjectEventSocket(
  projectId: string,
  options: {
    sessionId: string;
    lastSequence?: number;
    getLastSequence?: () => number;
  },
  handlers: SocketHandlers
): SocketManager {
  const manager = createEmptyManager();
  manager.projectId = projectId;
  manager.sessionId = options.sessionId;
  manager.lastSequence = Math.max(0, Math.floor(options.lastSequence ?? 0));
  manager.getLastSequence = options.getLastSequence;
  manager.handlers = handlers;
  manager.closedByClient = false;
  openManagedSocket(manager);
  return manager;
}

export function createCoreProjectEventSocket(
  projectId: string,
  options: {
    sessionId: string;
    lastSequence?: number;
  },
  handlers: {
    onEvent: OnEvent;
    onOpen?: OnOpen;
    onClose?: OnClose;
    onError?: OnError;
  }
): WebSocket {
  const socket = new WebSocket(
    buildSocketUrl(projectId, options.sessionId, Math.max(0, Math.floor(options.lastSequence ?? 0)))
  );

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
      // Ignore invalid event payloads.
    }
  });

  socket.addEventListener("close", (event) => {
    handlers.onClose?.(event);
  });

  socket.addEventListener("error", (event) => {
    handlers.onError?.(event);
  });

  return socket;
}
