/**
 * Entrocut Client - Preload 脚本
 *
 * 在渲染进程中暴露安全的 API，通过 contextBridge 实现。
 */

import { contextBridge, ipcRenderer } from 'electron';

// ============================================
// 类型定义
// ============================================

interface SceneSegment {
  start_frame: number;
  end_frame: number;
  start_time: number;
  end_time: number;
}

interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

interface DetectScenesResponse {
  total_frames: number;
  fps: number;
  duration: number;
  scenes: SceneSegment[];
}

interface ExtractedFrame {
  scene_index: number;
  frame_number: number;
  timestamp: number;
  file_path: string;
}

interface ExtractFramesResponse {
  video_path: string;
  extracted_frames: ExtractedFrame[];
}

interface SidecarAPI {
  health(): Promise<HealthResponse>;
  detectScenes(videoPath: string, threshold?: number): Promise<DetectScenesResponse>;
  extractFrames(videoPath: string, scenes: SceneSegment[], framesPerScene?: number): Promise<ExtractFramesResponse>;
}

interface ElectronAPI {
  sidecar: SidecarAPI;
  platform: string;
  versions: NodeJS.ProcessVersions;
}

// ============================================
// API 暴露
// ============================================

const sidecarAPI: SidecarAPI = {
  health: () => ipcRenderer.invoke('sidecar:health'),
  detectScenes: (videoPath: string, threshold?: number) =>
    ipcRenderer.invoke('sidecar:detect-scenes', videoPath, threshold),
  extractFrames: (videoPath: string, scenes: SceneSegment[], framesPerScene?: number) =>
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
// 类型声明 (供渲染进程 TypeScript 使用)
// ============================================

declare global {
  interface Window {
    electron: ElectronAPI;
  }
}

export {};
