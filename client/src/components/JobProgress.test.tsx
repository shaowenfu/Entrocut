import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { JobProgress } from './JobProgress';
import type { Job } from '../types/job';
import '@testing-library/jest-dom';

describe('JobProgress Component', () => {
  const mockJob: Job = {
    id: 'test-id-1234567890',
    state: 'RUNNING',
    phase: 'DETECTING_SCENES',
    progress: 45,
    video_path: '/tmp/test.mp4',
    created_at: '2026-02-07T10:00:00Z',
    updated_at: '2026-02-07T10:01:00Z'
  };

  it('renders correctly in running state', () => {
    render(<JobProgress job={mockJob} />);
    expect(screen.getByText(/ID:/i)).toBeInTheDocument();
    expect(screen.getByText(/test-id-1234567890/i)).toBeInTheDocument();
    expect(screen.getByText(/PHASE:/i)).toBeInTheDocument();
    expect(screen.getByText(/Detecting scene transitions/i)).toBeInTheDocument();
    expect(screen.getByText(/45%/i)).toBeInTheDocument();
  });

  it('renders error message in failed state with forensics', () => {
    const failedJob: Job = {
      ...mockJob,
      state: 'FAILED',
      error: {
        type: 'runtime_error',
        code: 'ERR_TEST',
        message: 'Something failed during test',
        step: 'DETECTING_SCENES',
        timestamp: new Date().toISOString()
      }
    };
    render(<JobProgress job={failedJob} />);
    expect(screen.getByText(/Something failed during test/i)).toBeInTheDocument();
    expect(screen.getByText(/TYPE:/i)).toBeInTheDocument();
    expect(screen.getByText(/runtime_error/i)).toBeInTheDocument();
    expect(screen.getByText(/CODE:/i)).toBeInTheDocument();
    expect(screen.getByText(/ERR_TEST/i)).toBeInTheDocument();
    expect(screen.getByText(/STEP:/i)).toBeInTheDocument();
    expect(screen.getByText(/DETECTING_SCENES/i)).toBeInTheDocument();
  });

  it('renders output video in succeeded state with HTTP protocol via Core', () => {
    const succeededJob: Job = {
      ...mockJob,
      state: 'SUCCEEDED',
      output_video: '/tmp/final.mp4'
    };
    render(<JobProgress job={succeededJob} />);
    expect(screen.getByText(/OUTPUT_READY/i)).toBeInTheDocument();
    expect(screen.getByText(/STATUS: PLAYABLE/i)).toBeInTheDocument();
    
    const videoElement = document.querySelector('video');
    expect(videoElement).toBeInTheDocument();
    // 应该使用 Core 端的 HTTP 地址，且路径经过编码
    expect(videoElement?.src).toBe('http://127.0.0.1:8000/videos/%2Ftmp%2Ffinal.mp4');
  });

  it('handles Chinese and space characters in output_video path', () => {
    const specialJob: Job = {
      ...mockJob,
      state: 'SUCCEEDED',
      output_video: '/home/user/视频/output video.mp4'
    };
    render(<JobProgress job={specialJob} />);
    
    const videoElement = document.querySelector('video');
    // 验证 encodeURIComponent 是否正确工作
    const expectedPath = encodeURIComponent('/home/user/视频/output video.mp4');
    expect(videoElement?.src).toBe(`http://127.0.0.1:8000/videos/${expectedPath}`);
  });
});
