/**
 * Sidecar 进程管理模块
 *
 * 负责 Python 算法服务的生命周期管理。
 */

import { spawn } from 'child_process';
import * as path from 'path';

let sidecarProcess: ReturnType<typeof spawn> | null = null;

// ============================================
// 配置
// ============================================

const CORE_PORT = '8000';
export const CORE_SERVER_URL = `http://127.0.0.1:${CORE_PORT}`;

/**
 * 获取 core 目录路径
 */
function getCorePath(): string {
  return path.resolve(__dirname, '../../core');
}

/**
 * 获取 Core 服务器的 Python 解释器路径
 */
function getCorePythonPath(): string {
  const corePath = getCorePath();
  const isWindows = process.platform === 'win32';
  return isWindows
    ? path.join(corePath, 'venv', 'Scripts', 'python.exe')
    : path.join(corePath, 'venv', 'bin', 'python');
}

// ============================================
// 进程管理
// ============================================

/**
 * 启动 Sidecar 进程
 */
export function startSidecar(): void {
  if (sidecarProcess) {
    console.warn('[Sidecar] Process already running');
    return;
  }

  const corePath = getCorePath();
  const pythonPath = getCorePythonPath();

  console.log(`[Sidecar] Starting: ${pythonPath} server.py`);

  sidecarProcess = spawn(pythonPath, ['server.py'], {
    cwd: corePath,
    env: { ...process.env, CORE_PORT, PYTHONUNBUFFERED: '1' },
  });

  sidecarProcess.stdout?.on('data', (data) => {
    console.log(`[Sidecar] ${data.toString().trim()}`);
  });

  sidecarProcess.stderr?.on('data', (data) => {
    const message = data.toString().trim();
    // 过滤掉 Uvicorn/Python 的 INFO 日志，不要作为 Error 输出
    if (message.includes('INFO:')) {
      console.log(`[Sidecar] ${message}`);
    } else {
      console.error(`[Sidecar Error] ${message}`);
    }
  });

  sidecarProcess.on('close', (code) => {
    console.log(`[Sidecar] Process exited with code ${code}`);
    sidecarProcess = null;
  });

  sidecarProcess.on('error', (error) => {
    console.error(`[Sidecar] Failed to start: ${error.message}`);
  });
}

/**
 * 停止 Sidecar 进程
 */
export function stopSidecar(): void {
  if (!sidecarProcess) {
    return;
  }

  console.log('[Sidecar] Stopping...');
  sidecarProcess.kill('SIGTERM');
  sidecarProcess = null;
}

/**
 * 检查 Sidecar 是否正在运行
 */
export function isSidecarRunning(): boolean {
  return sidecarProcess !== null;
}
