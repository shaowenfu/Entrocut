import React from 'react';
import type { Job, RunningPhase } from '../types/job';
import { Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';

interface JobProgressProps {
  job: Job;
}

const PHASE_LABELS: Record<RunningPhase, string> = {
  VALIDATING_INPUT: 'Validating video source...',
  DETECTING_SCENES: 'Detecting scene transitions...',
  EXTRACTING_FRAMES: 'Extracting key frames...',
  ANALYZING_MOCK: 'Analyzing visual content (Cloud Mock)...',
  GENERATING_EDL: 'Generating edit decision list...',
  RENDERING_OUTPUT: 'Rendering final output (FFmpeg)...',
  FINALIZING_RESULT: 'Finalizing artifacts...'
};

export const JobProgress: React.FC<JobProgressProps> = ({ job }) => {
  const isRunning = job.state === 'RUNNING';
  const isSucceeded = job.state === 'SUCCEEDED';
  const isFailed = job.state === 'FAILED';

  return (
    <div className="p-4 border border-border bg-[#121212] space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          {isRunning && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
          {isSucceeded && <CheckCircle2 className="w-4 h-4 text-primary" />}
          {isFailed && <AlertCircle className="w-4 h-4 text-error" />}
          <span className="font-bold uppercase tracking-wider">
            JOB: {job.id.slice(0, 8)}
          </span>
        </div>
        <span className={`text-xs px-2 py-0.5 border ${
          isSucceeded ? 'border-primary text-primary' : 
          isFailed ? 'border-error text-error' : 'border-foreground/50'
        }`}>
          {job.state}
        </span>
      </div>

      {isRunning && job.phase && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-foreground/70">
            <span>{PHASE_LABELS[job.phase]}</span>
            <span>{job.progress}%</span>
          </div>
          <div className="w-full h-1 bg-border overflow-hidden">
            <div 
              className="h-full bg-primary transition-all duration-500" 
              style={{ width: `${job.progress}%` }}
            />
          </div>
        </div>
      )}

      {isFailed && job.error && (
        <div className="p-2 border border-error bg-error/10 text-error text-xs space-y-1">
          <div className="font-bold">[{job.error.type}] {job.error.code}</div>
          <div>{job.error.message}</div>
        </div>
      )}

      {isSucceeded && job.output_video && (
        <div className="space-y-2">
          <div className="text-xs text-primary font-bold">OUTPUT_READY:</div>
          <div className="text-[10px] text-foreground/50 truncate">{job.output_video}</div>
          <video 
            controls 
            className="w-full border border-border mt-2"
            src={`file://${job.output_video}`}
          />
        </div>
      )}
    </div>
  );
};
