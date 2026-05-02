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

// core health check 的轮询间隔。
const HEALTH_RETRY_MS = 350;
// core 启动后等待 /health 就绪的最长时间。
const HEALTH_TIMEOUT_MS = 20_000;

// 当前托管的 core 子进程引用；非托管模式下保持 null。
let coreProcess: ChildProcessWithoutNullStreams | null = null;
// 标记当前退出是否由 Electron 主动触发，用于区分正常停止和异常崩溃。
let isStoppingCore = false;
// 暴露给 Renderer 的 core 运行态快照。
let runtimeState: CoreRuntimeState = {
  status: "idle",
  baseUrl: null,
  pid: null,
  lastError: null,
};
// core 状态订阅者；main.ts 用它把状态推送给 Renderer。
const listeners = new Set<(state: CoreRuntimeState) => void>();

// 广播当前 core 运行态给所有订阅者。
function emitState(): void {
  const snapshot = getCoreRuntimeState();
  for (const listener of listeners) {
    listener(snapshot);
  }
}

// 原子更新 runtimeState，并立即广播新状态。
function setRuntimeState(next: Partial<CoreRuntimeState>): void {
  runtimeState = {
    ...runtimeState,
    ...next,
  };
  emitState();
}

// 开发态是否由 Electron 自动托管 core；可用环境变量关闭。
function canManageCoreInDev(): boolean {
  return process.env.ENTROCUT_SKIP_MANAGED_CORE !== "1";
}

// 向系统申请一个当前可用的本地端口。
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

// 发布态内置 core 可执行文件路径。
function getCoreExecutablePath(): string {
  if (!app.isPackaged) {
    throw new Error("core_executable_path_not_available_in_dev");
  }
  const binaryName = process.platform === "win32" ? "entrocut-core.exe" : "entrocut-core";
  return path.join(process.resourcesPath, "core-dist", binaryName);
}

// 开发态推导仓库根目录，用于定位 core/。
function getDevCoreProjectRoot(): string {
  return path.resolve(app.getAppPath(), "..", "..");
}

// 开发态选择 Python 解释器：优先环境变量，其次 core/venv，最后系统 python。
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

// 按当前环境启动被 Electron 托管的 core 进程。
function spawnManagedCore(port: number): ChildProcessWithoutNullStreams {
  const env = {
    ...process.env,
    // core 从环境变量读取监听端口。
    CORE_PORT: String(port),
    // 桌面端 core 数据目录放在应用 userData 下，避免写入源码目录。
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
  // 开发态直接从 core/ 目录启动 FastAPI 服务。
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

// 轮询 core /health，直到服务可用或超时。
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

// 开发态非托管模式：连接外部已启动的 core，并只做健康检查。
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

// 启动 core：开发态可托管/非托管，发布态启动内置可执行文件。
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
    // 把 core 日志前缀化转发到 Electron 主进程日志。
    coreProcess.stdout.on("data", (chunk: Buffer) => {
      process.stdout.write(`[core] ${chunk.toString()}`);
    });
    coreProcess.stderr.on("data", (chunk: Buffer) => {
      process.stderr.write(`[core] ${chunk.toString()}`);
    });
    coreProcess.once("exit", (code, signal) => {
      const detail = `core_exit_${code ?? "null"}_${signal ?? "none"}`;
      // 主动停止视为 stopped；ready 后意外退出视为 failed。
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

// 停止当前托管的 core 进程；先 SIGTERM，超时后 SIGKILL。
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

// 返回当前 core 运行态副本，避免外部直接修改内部状态。
export function getCoreRuntimeState(): CoreRuntimeState {
  return { ...runtimeState };
}

// 订阅 core 运行态变化；注册后立即推送一次当前状态。
export function onCoreRuntimeState(listener: (state: CoreRuntimeState) => void): () => void {
  listeners.add(listener);
  listener(getCoreRuntimeState());
  return () => {
    listeners.delete(listener);
  };
}
