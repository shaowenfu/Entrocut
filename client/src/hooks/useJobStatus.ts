import { useQuery } from '@tanstack/react-query';
import type { Job } from '../types/job';

export function useJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ['job-status', jobId],
    queryFn: async () => {
      if (!jobId) return null;
      return await window.electron.job.getStatus(jobId);
    },
    enabled: !!jobId,
    refetchInterval: (query) => {
      const job = query.state.data as Job | undefined;
      if (!job || job.state === 'SUCCEEDED' || job.state === 'FAILED') {
        return false;
      }
      return 1000; // Poll every second while running
    },
  });
}

export function useJobList() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: async () => {
      return await window.electron.job.listAll();
    },
  });
}
