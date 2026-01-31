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

import { app, BrowserWindow, ipcMain } from 'electron';
import * as path from 'path';
import { spawn} from 'child_process';

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
 * 健康检查
 */
ipcMain.handle('sidecar:health', async () => {
  try {
    const response = await fetch(`${CORE_SERVER_URL}/health`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Sidecar health check failed: ${message}`);
  }
});

/**
 * 场景检测
 */
ipcMain.handle(
  'sidecar:detect-scenes',
  async (_event, videoPath: string, threshold?: number) => {
    try {
      const response = await fetch(`${CORE_SERVER_URL}/detect-scenes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_path: videoPath, threshold }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Scene detection failed: ${message}`);
    }
  }
);

/**
 * 抽帧
 */
ipcMain.handle(
  'sidecar:extract-frames',
  async (_event, videoPath: string, scenes: unknown[], framesPerScene?: number) => {
    try {
      const response = await fetch(`${CORE_SERVER_URL}/extract-frames`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_path: videoPath,
          scenes,
          frames_per_scene: framesPerScene ?? 3,
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Frame extraction failed: ${message}`);
    }
  }
);

// ============================================
// 应用生命周期
// ============================================

// 当 Electron 完成初始化时创建窗口
app.whenReady().then(() => {
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
