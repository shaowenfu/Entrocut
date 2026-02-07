import { useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TerminalHeader } from './components/TerminalHeader';
import { VideoUploader } from './components/VideoUploader';
import { JobProgress } from './components/JobProgress';
import { useJobStatus, useJobList } from './hooks/useJobStatus';
import type { Job } from './types/job';

const queryClient = new QueryClient();

function MainContent() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const { data: activeJob } = useJobStatus(activeJobId);
  const { data: history, refetch: refetchHistory } = useJobList();

  const handleStartJob = async (path: string) => {
    try {
      const result = await window.electron.job.start(path);
      setActiveJobId(result.job_id);
      refetchHistory();
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="flex flex-col h-screen max-h-screen">
      <TerminalHeader />
      
      <main className="flex-1 overflow-auto p-4 flex flex-col space-y-4">
        <section className="space-y-2">
          <div className="text-[10px] text-foreground/30 uppercase tracking-widest font-bold">01_SOURCE_INPUT</div>
          <VideoUploader 
            onStart={handleStartJob} 
            disabled={activeJob?.state === 'RUNNING'} 
          />
        </section>

        {activeJob && (
          <section className="space-y-2">
            <div className="text-[10px] text-foreground/30 uppercase tracking-widest font-bold">02_ACTIVE_PIPELINE</div>
            <JobProgress job={activeJob} />
          </section>
        )}

        <section className="space-y-2 flex-1">
          <div className="text-[10px] text-foreground/30 uppercase tracking-widest font-bold">03_HISTORY_LOG</div>
          <div className="border border-border divide-y divide-border overflow-auto max-h-[300px]">
            {history?.map((job: Job) => (
              <div 
                key={job.id} 
                className={`p-2 text-xs cursor-pointer hover:bg-white/5 flex justify-between items-center ${activeJobId === job.id ? 'bg-white/5 text-primary' : ''}`}
                onClick={() => setActiveJobId(job.id)}
              >
                <div className="flex space-x-4">
                  <span className="font-mono text-foreground/50">{new Date(job.created_at).toLocaleTimeString()}</span>
                  <span className="truncate max-w-[200px]">{job.video_path.split('/').pop()}</span>
                </div>
                <span className={job.state === 'SUCCEEDED' ? 'text-primary' : job.state === 'FAILED' ? 'text-error' : ''}>
                  {job.state}
                </span>
              </div>
            ))}
            {(!history || history.length === 0) && (
              <div className="p-4 text-center text-foreground/30 text-xs italic">NO_HISTORY_FOUND</div>
            )}
          </div>
        </section>
      </main>

      <footer className="p-2 border-t border-border bg-[#0a0a0a] flex justify-between items-center text-[10px] text-foreground/50">
        <div>SYS_OS: {window.electron.platform}</div>
        <div>CONNECTION: LOCALHOST:8000</div>
      </footer>
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <MainContent />
    </QueryClientProvider>
  );
}

export default App;