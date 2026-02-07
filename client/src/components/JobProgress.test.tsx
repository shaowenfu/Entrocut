import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { JobProgress } from './JobProgress';
import type { Job } from '../types/job';
import '@testing-library/jest-dom';

describe('JobProgress Component', () => {
  const mockJob: Job = {
    id: 'test-id-12345678',
    state: 'RUNNING',
    phase: 'DETECTING_SCENES',
    progress: 45,
    video_path: '/tmp/test.mp4',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  };

  it('renders correctly in running state', () => {
    render(<JobProgress job={mockJob} />);
    expect(screen.getByText(/JOB: test-id/i)).toBeInTheDocument();
    expect(screen.getByText(/Detecting scene transitions/i)).toBeInTheDocument();
    expect(screen.getByText(/45%/i)).toBeInTheDocument();
  });

  it('renders error message in failed state', () => {
    const failedJob: Job = {
      ...mockJob,
      state: 'FAILED',
      error: {
        type: 'runtime_error',
        code: 'ERR_TEST',
        message: 'Something failed during test',
        timestamp: new Date().toISOString()
      }
    };
    render(<JobProgress job={failedJob} />);
    expect(screen.getByText(/Something failed during test/i)).toBeInTheDocument();
    expect(screen.getByText(/\[runtime_error\] ERR_TEST/i)).toBeInTheDocument();
  });

  it('renders output video in succeeded state', () => {
    const succeededJob: Job = {
      ...mockJob,
      state: 'SUCCEEDED',
      output_video: '/tmp/final.mp4'
    };
    render(<JobProgress job={succeededJob} />);
    expect(screen.getByText(/OUTPUT_READY:/i)).toBeInTheDocument();
    // Note: in JSDOM, video element might not be fully functional but we can check if it's rendered
  });
});
