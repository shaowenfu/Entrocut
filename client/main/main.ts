/**
 * Entrocut Client - Electron 主进程入口
 *
 * 负责：
 * - 创建应用窗口
 * - 管理应用生命周期
 * - 与 Sidecar 进程通信
 *
 * 注意：此文件编译为 CommonJS 格式，供 Electron 主进程使用
 */

import { app, BrowserWindow, ipcMain, dialog, protocol, net } from 'electron';
import * as path from 'path';
import { spawn } from 'child_process';
import { pathToFileURL } from 'url';
import { initDb, saveJob, getJob, getAllJobs } from './db';
import type { Job } from '../src/types/job';

// 屏蔽 Chromium 内部不重要的日志 (如 DBus 错误)
app.commandLine.appendSwitch('log-level', '3');
app.commandLine.appendSwitch('disable-gpu-rasterization');

// ============================================
// 配置
// ============================================

const IS_DEV = process.env.ELECTRON_IS_DEV === 'true';
const VITE_DEV_SERVER_URL = 'http://localhost:5173';
const CORE_SERVER_URL = 'http://127.0.0.1:8000';

// ============================================
// 全局状态
// ============================================

let mainWindow: BrowserWindow | null = null;
let sidecarProcess: ReturnType<typeof spawn> | null = null;

type JobStartResponse = {
  job_id: string;
  error?: {
    message?: string;
  };
};

type CoreJobStatusResponse = {
  job_id: string;
  job_state?: Job['state'];
  state?: Job['state'];
  running_phase?: Job['phase'];
  phase?: Job['phase'];
  progress: number;
  error?: Job['error'];
  artifacts?: {
    output_video?: string;
  };
  output_video?: string;
};

// ============================================
// 工具函数
// ============================================

/**
 * 获取 preload 文件路径
 */
function getPreloadPath(): string {
  return path.join(__dirname, 'preload.cjs');
}

/**
 * 获取前端页面路径
 */
function getLoadUrl(): string {
  if (IS_DEV) {
    return VITE_DEV_SERVER_URL;
  }
  // 生产环境：打包后的 index.html
  return path.join(__dirname, '../dist/index.html');
}

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
// 窗口管理
// ============================================

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    backgroundColor: '#1a1a1a',
    show: false,
    webPreferences: {
      preload: getPreloadPath(),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  // 加载页面
  const loadUrl = getLoadUrl();
  if (IS_DEV) {
    mainWindow.loadURL(loadUrl);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(loadUrl);
  }

  // 窗口准备好后显示
  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  // 窗口关闭时清理
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 开发环境：导航失败时提示
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
    console.error('Failed to load:', errorCode, errorDescription);
  });
}

// ============================================
// Sidecar 进程管理
// ============================================

function startSidecar(): void {
  if (sidecarProcess) {
    console.warn('[Sidecar] Process already running');
    return;
  }

  const corePath = getCorePath();
  const pythonPath = getCorePythonPath();

  console.log(`[Sidecar] Starting: ${pythonPath} server.py`);

  sidecarProcess = spawn(pythonPath, ['server.py'], {
    cwd: corePath,
    env: { ...process.env, CORE_PORT: '8000', PYTHONUNBUFFERED: '1' },
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

function stopSidecar(): void {
  if (!sidecarProcess) {
    return;
  }

  console.log('[Sidecar] Stopping...');
  sidecarProcess.kill('SIGTERM');
  sidecarProcess = null;
}

// ============================================
// IPC 通信
// ============================================

/**
 * 选择视频文件
 */
ipcMain.handle('file:select-video', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: 'Videos', extensions: ['mp4', 'avi', 'mov', 'mkv'] }]
  });
  return result.filePaths[0];
});

/**
 * 启动任务
 */
ipcMain.handle('job:start', async (_event, videoPath: string) => {
  try {
    const response = await fetch(`${CORE_SERVER_URL}/jobs/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_path: videoPath }),
    });
    const result = (await response.json()) as JobStartResponse;
    
    if (response.status === 409) {
      throw new Error('JOB_ALREADY_RUNNING');
    }

    if (!response.ok) {
      throw new Error(result.error?.message || `HTTP ${response.status}`);
    }
    
    // 初始保存到 SQLite
    saveJob({
      id: result.job_id,
      state: 'RUNNING',
      video_path: videoPath,
      phase: 'VALIDATING_INPUT'
    });

    return result;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(message);
  }
});

/**
 * 获取任务状态 (投影到 SQLite)
 */
ipcMain.handle('job:get-status', async (_event, jobId: string) => {
  try {
    const response = await fetch(`${CORE_SERVER_URL}/jobs/${jobId}`);
    if (response.status === 404) {
      // 任务在 Core 中不存在，可能已重启，返回本地缓存
      return getJob(jobId);
    }
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    const status = (await response.json()) as CoreJobStatusResponse;
    
    // 统一字段映射（兼容 Core 新旧字段，避免跨端漂移导致状态丢失）
    saveJob({
      id: status.job_id,
      state: status.job_state ?? status.state,
      phase: status.running_phase ?? status.phase,
      progress: status.progress,
      error: status.error,
      output_video: status.artifacts?.output_video ?? status.output_video
    });

    return getJob(jobId);
  } catch {
    return getJob(jobId);
  }
});

/**
 * 获取所有历史任务
 */
ipcMain.handle('job:list-all', async () => {
  return getAllJobs();
});

/**
 * 取消任务
 */
ipcMain.handle('job:cancel', async (_event, jobId: string) => {
  try {
    const response = await fetch(`${CORE_SERVER_URL}/jobs/${jobId}/cancel`, {
      method: 'POST'
    });
    return await response.json();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Failed to cancel job: ${message}`);
  }
});

/**
 * 健康检查
 */
ipcMain.handle('sidecar:health', async () => {
  try {
    const response = await fetch(`${CORE_SERVER_URL}/health`);
    return await response.json();
  } catch {
    throw new Error('Sidecar unavailable');
  }
});

// ============================================
// 应用生命周期
// ============================================

// 当 Electron 完成初始化时创建窗口
app.whenReady().then(() => {
  // 注册自定义媒体协议以支持本地播放
  protocol.handle('media', (request) => {
    try {
      const rawPath = request.url.replace(/^media:\/\//, '');
      const decodedPath = decodeURIComponent(rawPath);
      const fileUrl = pathToFileURL(decodedPath).toString();
      return net.fetch(fileUrl, {
        method: request.method,
        headers: request.headers,
        bypassCustomProtocolHandlers: true
      });
    } catch (e) {
      console.error('[Protocol] Error:', e);
      return new Response('Protocol Error', { status: 500 });
    }
  });

  initDb();
  createWindow();
  startSidecar();

  // macOS: 当点击 dock 图标且没有其他窗口打开时，重新创建窗口
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// 当所有窗口都关闭时退出应用（macOS 除外）
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// 应用退出前清理
app.on('before-quit', () => {
  stopSidecar();
});

// ============================================
// 导出
// ============================================

export { mainWindow, sidecarProcess };
