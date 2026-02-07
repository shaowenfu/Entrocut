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
      // 停止轮询条件：任务不存在、成功或失败
      if (!job || job.state === 'SUCCEEDED' || job.state === 'FAILED') {
        return false;
      }
      return 1000;
    },
  });
}

export function useJobList() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: async () => {
      return await window.electron.job.listAll();
    },
    refetchInterval: 5000, // 每5秒刷新一次历史列表
  });
}
