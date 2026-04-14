import { existsSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { app } from "electron";

export type CoreSupervisorStatus = "idle" | "starting" | "ready" | "failed" | "stopped";

export interface CoreRuntimeState {
  status: CoreSupervisorStatus;
  baseUrl: string | null;
  pid: number | null;
  lastError: string | null;
}

const HEALTH_RETRY_MS = 350;
const HEALTH_TIMEOUT_MS = 20_000;

let coreProcess: ChildProcessWithoutNullStreams | null = null;
let isStoppingCore = false;
let runtimeState: CoreRuntimeState = {
  status: "idle",
  baseUrl: null,
  pid: null,
  lastError: null,
};
const listeners = new Set<(state: CoreRuntimeState) => void>();

function emitState(): void {
  const snapshot = getCoreRuntimeState();
  for (const listener of listeners) {
    listener(snapshot);
  }
}

function setRuntimeState(next: Partial<CoreRuntimeState>): void {
  runtimeState = {
    ...runtimeState,
    ...next,
  };
  emitState();
}

function canManageCoreInDev(): boolean {
  return process.env.ENTROCUT_SKIP_MANAGED_CORE !== "1";
}

async function reservePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close(() => reject(new Error("core_port_resolve_failed")));
        return;
      }
      const port = address.port;
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve(port);
      });
    });
  });
}

function getCoreExecutablePath(): string {
  if (!app.isPackaged) {
    throw new Error("core_executable_path_not_available_in_dev");
  }
  const binaryName = process.platform === "win32" ? "entrocut-core.exe" : "entrocut-core";
  return path.join(process.resourcesPath, "core-dist", binaryName);
}

function getDevCoreProjectRoot(): string {
  return path.resolve(app.getAppPath(), "..", "..");
}

function getDevPythonBin(devCoreRoot: string): string {
  const configured = process.env.CORE_PYTHON_BIN?.trim();
  if (configured) {
    return configured;
  }

  const venvPython =
    process.platform === "win32"
      ? path.join(devCoreRoot, "core", "venv", "Scripts", "python.exe")
      : path.join(devCoreRoot, "core", "venv", "bin", "python");
  if (existsSync(venvPython)) {
    return venvPython;
  }
  return "python";
}

function spawnManagedCore(port: number): ChildProcessWithoutNullStreams {
  const env = {
    ...process.env,
    CORE_PORT: String(port),
    ENTROCUT_APP_DATA_ROOT: path.join(app.getPath("userData"), "core-data"),
  };

  if (app.isPackaged) {
    const executablePath = getCoreExecutablePath();
    return spawn(executablePath, [], {
      env,
      stdio: "pipe",
      windowsHide: true,
    });
  }

  const devCoreRoot = getDevCoreProjectRoot();
  const pythonBin = getDevPythonBin(devCoreRoot);
  return spawn(
    pythonBin,
    ["-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", String(port)],
    {
      cwd: path.join(devCoreRoot, "core"),
      env,
      stdio: "pipe",
      windowsHide: true,
    }
  );
}

async function waitForHealth(baseUrl: string): Promise<void> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < HEALTH_TIMEOUT_MS) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) {
        return;
      }
    } catch {
      // noop
    }
    await new Promise((resolve) => setTimeout(resolve, HEALTH_RETRY_MS));
  }
  throw new Error("core_health_check_timeout");
}

async function startUnmanagedCoreFromEnv(): Promise<CoreRuntimeState> {
  const configuredBaseUrl = process.env.VITE_CORE_BASE_URL?.trim();
  if (!configuredBaseUrl) {
    throw new Error("missing_VITE_CORE_BASE_URL_for_unmanaged_dev_core");
  }
  setRuntimeState({ status: "starting", baseUrl: configuredBaseUrl, lastError: null, pid: null });
  await waitForHealth(configuredBaseUrl);
  setRuntimeState({ status: "ready" });
  return getCoreRuntimeState();
}

export async function startCore(): Promise<CoreRuntimeState> {
  if (runtimeState.status === "ready" || runtimeState.status === "starting") {
    return getCoreRuntimeState();
  }

  if (!app.isPackaged && !canManageCoreInDev()) {
    return startUnmanagedCoreFromEnv();
  }

  const port = await reservePort();
  const baseUrl = `http://127.0.0.1:${port}`;

  setRuntimeState({
    status: "starting",
    baseUrl,
    lastError: null,
    pid: null,
  });

  try {
    coreProcess = spawnManagedCore(port);
    setRuntimeState({ pid: coreProcess.pid ?? null });
    coreProcess.stdout.on("data", (chunk: Buffer) => {
      process.stdout.write(`[core] ${chunk.toString()}`);
    });
    coreProcess.stderr.on("data", (chunk: Buffer) => {
      process.stderr.write(`[core] ${chunk.toString()}`);
    });
    coreProcess.once("exit", (code, signal) => {
      const detail = `core_exit_${code ?? "null"}_${signal ?? "none"}`;
      const state = isStoppingCore ? "stopped" : runtimeState.status === "ready" ? "failed" : "stopped";
      setRuntimeState({ status: state, pid: null, lastError: isStoppingCore ? null : detail });
      isStoppingCore = false;
      coreProcess = null;
    });

    await waitForHealth(baseUrl);
    setRuntimeState({ status: "ready", lastError: null });
    return getCoreRuntimeState();
  } catch (error) {
    const message = error instanceof Error ? error.message : "core_start_failed";
    setRuntimeState({ status: "failed", lastError: message, pid: null });
    throw error;
  }
}

export async function stopCore(): Promise<void> {
  const current = coreProcess;
  coreProcess = null;
  isStoppingCore = true;

  if (!current || current.killed) {
    isStoppingCore = false;
    setRuntimeState({ status: "stopped", pid: null });
    return;
  }

  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      try {
        current.kill("SIGKILL");
      } catch {
        // noop
      }
    }, 3_000);

    current.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });

    try {
      current.kill("SIGTERM");
    } catch {
      isStoppingCore = false;
      clearTimeout(timer);
      resolve();
    }
  });

  setRuntimeState({ status: "stopped", pid: null });
}

export function getCoreRuntimeState(): CoreRuntimeState {
  return { ...runtimeState };
}

export function onCoreRuntimeState(listener: (state: CoreRuntimeState) => void): () => void {
  listeners.add(listener);
  listener(getCoreRuntimeState());
  return () => {
    listeners.delete(listener);
  };
}
