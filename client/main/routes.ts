/**
 * IPC 路由模块
 * 
 * 封装前端与主进程、Core 服务及数据库之间的通信逻辑。
 */

import { ipcMain, dialog } from 'electron';
import { saveJob, getJob, getAllJobs } from './db';
import { CORE_SERVER_URL } from './sidecar';
import type { Job } from '../src/types/job';

// ============================================
// 类型定义
// ============================================

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
// 路由注册
// ============================================

/**
 * 注册所有的 IPC Handler
 */
export function registerIpcHandlers(): void {
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
      console.error('[IPC] job:start failed:', message);
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
    } catch (error) {
      console.warn(`[IPC] job:get-status failed for ${jobId}, falling back to DB:`, error);
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
      console.error('[IPC] job:cancel failed:', message);
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
    } catch (error) {
      console.error('[IPC] sidecar:health failed:', error);
      throw new Error('Sidecar unavailable');
    }
  });
}
