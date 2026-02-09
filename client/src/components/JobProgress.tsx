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
  const [videoError, setVideoError] = React.useState<string | null>(null);

  const videoUrl = job.output_video 
    ? `media://${encodeURIComponent(job.output_video)}`
    : '';

  React.useEffect(() => {
    setVideoError(null);
  }, [videoUrl]);

  return (
    <div className="p-4 border border-border bg-[#121212] space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex flex-col">
          <div className="flex items-center space-x-2">
            {isRunning && <Loader2 className="w-4 h-4 animate-spin text-primary" />}
            {isSucceeded && <CheckCircle2 className="w-4 h-4 text-primary" />}
            {isFailed && <AlertCircle className="w-4 h-4 text-error" />}
            <span className="font-bold uppercase tracking-wider">
              ID: {job.id}
            </span>
          </div>
          <span className="text-[10px] text-foreground/30 mt-1">
            CREATED_AT: {new Date(job.created_at).toLocaleString()}
            {isSucceeded || isFailed ? ` | FINALIZED: ${new Date(job.updated_at).toLocaleTimeString()}` : ''}
          </span>
        </div>
        <span className={`text-xs px-2 py-0.5 border ${
          isSucceeded ? 'border-primary text-primary' : 
          isFailed ? 'border-error text-error' : 'border-foreground/50'
        }`}>
          {job.state}
        </span>
      </div>

      {(isRunning || isSucceeded || isFailed) && job.phase && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-foreground/70">
            <span>PHASE: {PHASE_LABELS[job.phase]}</span>
            {isRunning && <span>{job.progress}%</span>}
          </div>
          {isRunning && (
            <div className="w-full h-1 bg-border overflow-hidden">
              <div 
                className="h-full bg-primary transition-all duration-500" 
                style={{ width: `${job.progress}%` }}
              />
            </div>
          )}
        </div>
      )}

      {isFailed && job.error && (
        <div className="p-2 border border-error bg-error/10 text-error text-[11px] space-y-2 font-mono">
          <div className="flex justify-between border-b border-error/30 pb-1">
            <span className="font-bold">TYPE: {job.error.type}</span>
            <span className="font-bold">CODE: {job.error.code}</span>
          </div>
          <div><span className="opacity-70">MESSAGE:</span> {job.error.message}</div>
          {job.error.step && <div><span className="opacity-70">STEP:</span> {job.error.step}</div>}
          {job.error.request_id && <div className="text-[9px] opacity-50">REQ_ID: {job.error.request_id}</div>}
        </div>
      )}

      {isSucceeded && job.output_video && (
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-xs text-primary font-bold">OUTPUT_READY</span>
            <span className={`text-[9px] ${videoError ? 'text-error' : 'text-primary/50'}`}>
              {videoError ? `PLAYBACK_ERR: ${videoError}` : 'STATUS: PLAYABLE'}
            </span>
          </div>
          <div className="text-[10px] text-foreground/40 bg-black/30 p-1 truncate border border-border/30">
            PATH: {job.output_video}
          </div>
          <video
            controls
            className="w-full border border-border mt-2 bg-black"
            src={videoUrl}
            onError={(e) => {
              const video = e.target as HTMLVideoElement;
              setVideoError(video.error?.message || 'Playback failed');
            }}
          />
        </div>
      )}
    </div>
  );
};
