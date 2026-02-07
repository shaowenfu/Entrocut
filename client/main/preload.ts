import { contextBridge, ipcRenderer } from 'electron';
import type { Job } from '../src/types/job';

interface ElectronAPI {
  file: {
    selectVideo(): Promise<string>;
  };
  job: {
    start(videoPath: string): Promise<{ job_id: string }>;
    getStatus(jobId: string): Promise<Job | undefined>;
    listAll(): Promise<Job[]>;
    cancel(jobId: string): Promise<any>;
  };
  sidecar: {
    health(): Promise<any>;
  };
  platform: string;
}

const electronAPI: ElectronAPI = {
  file: {
    selectVideo: () => ipcRenderer.invoke('file:select-video'),
  },
  job: {
    start: (videoPath: string) => ipcRenderer.invoke('job:start', videoPath),
    getStatus: (jobId: string) => ipcRenderer.invoke('job:get-status', jobId),
    listAll: () => ipcRenderer.invoke('job:list-all'),
    cancel: (jobId: string) => ipcRenderer.invoke('job:cancel', jobId),
  },
  sidecar: {
    health: () => ipcRenderer.invoke('sidecar:health'),
  },
  platform: process.platform,
};

contextBridge.exposeInMainWorld('electron', electronAPI);

declare global {
  interface Window {
    electron: ElectronAPI;
  }
}