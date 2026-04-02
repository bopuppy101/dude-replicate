/** WebSocket hook for real-time job metrics. */

import { useEffect, useRef, useState } from 'react';

export interface JobMetrics {
  job_id: number;
  status: string;
  timestamp?: string;
  cycle?: number;
  rows_this_cycle?: number;
  rows_total?: number;
  by_table?: Record<string, { I: number; U: number; D: number }>;
  checkpoint?: string;
  started_at?: string;
  errors?: number;
  last_error?: string | null;
}

export function useJobMetrics(jobId: number | null): JobMetrics | null {
  const [metrics, setMetrics] = useState<JobMetrics | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (jobId === null) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/jobs/${jobId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        setMetrics(JSON.parse(event.data));
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      // Reconnect after 3 seconds
      setTimeout(() => {
        if (wsRef.current === ws) {
          setMetrics(null);
        }
      }, 3000);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [jobId]);

  return metrics;
}

export interface DashboardSummary {
  jobs: Array<{ job_id: number; status: string; rows_total: number }>;
}

export function useDashboardMetrics(): DashboardSummary | null {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/dashboard`;
    const ws = new WebSocket(url);

    ws.onmessage = (event) => {
      try {
        setSummary(JSON.parse(event.data));
      } catch { /* ignore */ }
    };

    return () => ws.close();
  }, []);

  return summary;
}
