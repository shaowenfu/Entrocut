export type JobState = 'IDLE' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';

export type RunningPhase =
  | 'VALIDATING_INPUT'
  | 'DETECTING_SCENES'
  | 'EXTRACTING_FRAMES'
  | 'ANALYZING_MOCK'
  | 'GENERATING_EDL'
  | 'RENDERING_OUTPUT'
  | 'FINALIZING_RESULT';

export interface JobError {
  type: 'validation_error' | 'runtime_error' | 'external_error';
  code: string;
  message: string;
  step?: string;
  details?: Record<string, unknown>;
  request_id?: string;
  timestamp?: string;
}

export interface Job {
  id: string;
  state: JobState;
  phase?: RunningPhase;
  progress: number;
  video_path: string;
  output_video?: string;
  error?: JobError;
  created_at: string;
  updated_at: string;
}

export interface StartJobRequest {
  video_path: string;
}

export interface StatusReport {
  job_id: string;
  job_state: JobState;
  running_phase: RunningPhase;
  progress: number;
  error?: JobError;
  artifacts?: {
    output_video?: string;
  };
}
