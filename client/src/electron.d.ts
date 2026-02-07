import type { Job } from './types/job';

interface ElectronAPI {
  file: {
    selectVideo(): Promise<string>;
  };
  job: {
    start(videoPath: string): Promise<{ job_id: string }>;
    getStatus(jobId: string): Promise<Job | undefined>;
    listAll(): Promise<Job[]>;
    cancel(jobId: string): Promise<unknown>;
  };
  sidecar: {
    health(): Promise<unknown>;
  };
  platform: string;
}

declare global {
  interface Window {
    electron: ElectronAPI;
  }
}

export {};
