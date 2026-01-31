/**
 * Entrocut Client - Electron 主进程入口
 *
 * 负责：
 * - 创建应用窗口
 * - 管理应用生命周期
 * - 与 Sidecar 进程通信
 */

import { app, BrowserWindow, ipcMain } from 'electron';
import * as path from 'path';
import { spawn } from 'child_process';

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
// 窗口管理
// ============================================

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    backgroundColor: '#1a1a1a',
    show: false, // 等待加载完成后再显示
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // 加载页面
  if (IS_DEV) {
    mainWindow.loadURL(VITE_DEV_SERVER_URL);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // 窗口准备好后显示
  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  // 窗口关闭时清理
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ============================================
// Sidecar 进程管理
// ============================================

function startSidecar(): void {
  // 启动 Python Sidecar 进程
  const corePath = path.join(__dirname, '../../core');
  sidecarProcess = spawn('python', ['server.py'], {
    cwd: corePath,
    env: { ...process.env, CORE_PORT: '8000' },
  });

  sidecarProcess.stdout?.on('data', (data) => {
    console.log(`[Sidecar] ${data}`);
  });

  sidecarProcess.stderr?.on('data', (data) => {
    console.error(`[Sidecar Error] ${data}`);
  });

  sidecarProcess.on('close', (code) => {
    console.log(`[Sidecar] Process exited with code ${code}`);
    sidecarProcess = null;
  });
}

function stopSidecar(): void {
  if (sidecarProcess) {
    sidecarProcess.kill();
    sidecarProcess = null;
  }
}

// ============================================
// IPC 通信
// ============================================

// 健康检查
ipcMain.handle('sidecar:health', async () => {
  try {
    const response = await fetch(`${CORE_SERVER_URL}/health`);
    return await response.json();
  } catch (error) {
    throw new Error(`Sidecar health check failed: ${error}`);
  }
});

// 场景检测
ipcMain.handle('sidecar:detect-scenes', async (_, videoPath: string, threshold?: number) => {
  try {
    const response = await fetch(`${CORE_SERVER_URL}/detect-scenes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_path: videoPath, threshold }),
    });
    return await response.json();
  } catch (error) {
    throw new Error(`Scene detection failed: ${error}`);
  }
});

// 抽帧
ipcMain.handle('sidecar:extract-frames', async (_, videoPath: string, scenes: any[], framesPerScene?: number) => {
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
    return await response.json();
  } catch (error) {
    throw new Error(`Frame extraction failed: ${error}`);
  }
});

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
