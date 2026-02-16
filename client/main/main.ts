/**
 * Entrocut Client - Electron 主进程入口
 *
 * 负责：
 * - 应用生命周期管理
 * - 窗口管理
 * - 协调各模块 (DB, Sidecar, IPC Routes)
 */

import { app, BrowserWindow } from 'electron';
import * as path from 'path';
import { initDb } from './db';
import { startSidecar, stopSidecar } from './sidecar';
import { registerIpcHandlers } from './routes';

// 屏蔽 Chromium 内部不重要的日志
app.commandLine.appendSwitch('log-level', '3');
app.commandLine.appendSwitch('disable-gpu-rasterization');

// ============================================
// 配置
// ============================================

const IS_DEV = process.env.ELECTRON_IS_DEV === 'true';
const VITE_DEV_SERVER_URL = 'http://localhost:5173';

// ============================================
// 全局状态
// ============================================

let mainWindow: BrowserWindow | null = null;

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
  return path.join(__dirname, '../dist/index.html');
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
    backgroundColor: '#0b0b0b', // 对齐 Hacker 审美
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

  // 导航失败提示
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
    console.error('[Main] Failed to load:', errorCode, errorDescription);
  });
}

// ============================================
// 应用生命周期
// ============================================

app.whenReady().then(() => {
  console.log('[Main] App starting...');
  
  // 1. 初始化数据库
  initDb();
  
  // 2. 注册 IPC 路由
  registerIpcHandlers();
  
  // 3. 启动 Sidecar
  startSidecar();
  
  // 4. 创建窗口
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  console.log('[Main] App quitting...');
  stopSidecar();
});

// 导出供可能的跨模块引用
export { mainWindow };
