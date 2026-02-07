import { describe, it, expect, vi, beforeEach } from 'vitest';
import { initDb, saveJob, getJob } from './db';

// Mock electron app
vi.mock('electron', () => ({
  app: {
    getPath: vi.fn().mockReturnValue('./test-data'),
  },
}));

describe('Database Logic', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    initDb(':memory:');
  });

  it('should save and retrieve a job', () => {
    const job = {
      id: 'test-job-1',
      state: 'RUNNING' as const,
      video_path: '/path/to/video.mp4',
      phase: 'DETECTING_SCENES' as const,
      progress: 50
    };

    saveJob(job);
    const retrieved = getJob('test-job-1');

    expect(retrieved).toBeDefined();
    expect(retrieved?.state).toBe('RUNNING');
    expect(retrieved?.progress).toBe(50);
  });

  it('should update an existing job', () => {
    const job = {
      id: 'test-job-2',
      state: 'RUNNING' as const,
      video_path: '/path/to/video.mp4'
    };

    saveJob(job);
    saveJob({ id: 'test-job-2', progress: 100, state: 'SUCCEEDED' });

    const retrieved = getJob('test-job-2');
    expect(retrieved?.progress).toBe(100);
    expect(retrieved?.state).toBe('SUCCEEDED');
  });

  it('should handle errors correctly', () => {
    const error = {
      type: 'runtime_error' as const,
      code: 'ERR_123',
      message: 'Something went wrong',
      timestamp: new Date().toISOString()
    };

    saveJob({
      id: 'test-job-3',
      state: 'FAILED',
      video_path: '/path/to/video.mp4',
      error
    });

    const retrieved = getJob('test-job-3');
    expect(retrieved?.error).toEqual(error);
  });
});
