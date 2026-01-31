/**
 * Entrocut Client - Preload 脚本
 *
 * 在渲染进程中暴露安全的 API，通过 contextBridge 实现。
 */

import { contextBridge, ipcRenderer } from 'electron';

// ============================================
// 类型定义
// ============================================

interface SidecarAPI {
  health(): Promise<{ status: string; service: string; version: string }>;
  detectScenes(videoPath: string, threshold?: number): Promise<any>;
  extractFrames(videoPath: string, scenes: any[], framesPerScene?: number): Promise<any>;
}

interface ElectronAPI {
  sidecar: SidecarAPI;
  platform: string;
  versions: typeof process.versions;
}

// ============================================
// API 暴露
// ============================================

const sidecarAPI: SidecarAPI = {
  health: () => ipcRenderer.invoke('sidecar:health'),
  detectScenes: (videoPath: string, threshold?: number) =>
    ipcRenderer.invoke('sidecar:detect-scenes', videoPath, threshold),
  extractFrames: (videoPath: string, scenes: any[], framesPerScene?: number) =>
    ipcRenderer.invoke('sidecar:extract-frames', videoPath, scenes, framesPerScene),
};

const electronAPI: ElectronAPI = {
  sidecar: sidecarAPI,
  platform: process.platform,
  versions: process.versions,
};

// 暴露到 window.electron
contextBridge.exposeInMainWorld('electron', electronAPI);

// ============================================
// 类型声明 (供 TypeScript 使用)
// ============================================

declare global {
  interface Window {
    electron: ElectronAPI;
  }
}
