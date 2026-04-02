import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useJobMetrics } from '../api/websocket';

interface Job {
  id: number; name: string; source_endpoint_id: number; target_endpoint_id: number;
  job_type: string; status: string; pid: number | null; started_at: string | null;
  table_list: string[] | null; poll_interval: number; batch_size: number;
  current_run_id: number | null; heartbeat_at: string | null;
  checkpoint: string | null; live_metrics: Record<string, unknown> | null;
}

interface Endpoint { id: number; name: string; db_type: string; host: string; port: number; database_name: string | null; }

interface JobRun {
  id: number; run_type: string; status: string; started_at: string; ended_at: string | null;
  rows_total: number; rows_inserted: number; rows_updated: number; rows_deleted: number;
  error_count: number; avg_rows_per_sec: number | null; checkpoint_start: string | null;
  checkpoint_end: string | null; last_error: string | null;
}

const statusBadge: Record<string, string> = {
  running: 'bg-status-running/15 text-status-running border-status-running/30',
  stopped: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  error: 'bg-status-error/15 text-status-error border-status-error/30',
  stopping: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  completed: 'bg-status-completed/15 text-status-completed border-status-completed/30',
  cancelled: 'bg-surface-3/30 text-text-muted border-surface-3/50',
  failed: 'bg-status-error/15 text-status-error border-status-error/30',
};

const dbTypeLabel: Record<string, string> = {
  sqlserver: 'SQL Server',
  oracle: 'Oracle',
  postgresql: 'PostgreSQL',
};

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const jobId = parseInt(id!);
  const queryClient = useQueryClient();

  const { data: job } = useQuery<Job>({
    queryKey: ['job', jobId],
    queryFn: () => api.get(`/jobs/${jobId}`),
    refetchInterval: 3000,
  });

  const { data: endpoints = [] } = useQuery<Endpoint[]>({
    queryKey: ['endpoints'],
    queryFn: () => api.get('/endpoints'),
  });

  const { data: runs = [] } = useQuery<JobRun[]>({
    queryKey: ['job-runs', jobId],
    queryFn: () => api.get(`/jobs/${jobId}/runs`),
    refetchInterval: 10000,
  });

  const { data: logsData } = useQuery<{ lines: string[] }>({
    queryKey: ['job-logs', jobId],
    queryFn: () => api.get(`/jobs/${jobId}/logs?lines=50`),
    refetchInterval: 3000,
  });

  const wsMetrics = useJobMetrics(jobId);

  const actionMutation = useMutation({
    mutationFn: (action: string) => api.post(`/jobs/${jobId}/${action}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['job', jobId] }),
  });

  if (!job) return <p className="text-text-muted">Loading...</p>;

  const isRunning = job.status === 'running';

  // Merge metrics: prefer websocket (real-time), fall back to polled API data
  const lm = job.live_metrics as Record<string, any> | null;
  const m = {
    rows_total: wsMetrics?.rows_total ?? lm?.rows_total ?? 0,
    rows_this_cycle: wsMetrics?.rows_this_cycle ?? lm?.rows_this_cycle ?? 0,
    cycle: wsMetrics?.cycle ?? lm?.cycle ?? 0,
    checkpoint: wsMetrics?.checkpoint ?? job.checkpoint ?? '-',
    errors: wsMetrics?.errors ?? lm?.errors ?? 0,
    by_table: wsMetrics?.by_table ?? lm?.by_table ?? {},
    started_at: wsMetrics?.started_at ?? lm?.started_at,
    cycle_duration_ms: lm?.cycle_duration_ms ?? null,
    lag_ms: lm?.lag_ms ?? null,
  };

  // Resolve endpoints
  const sourceEp = endpoints.find((e) => e.id === job.source_endpoint_id);
  const targetEp = endpoints.find((e) => e.id === job.target_endpoint_id);

  const formatDuration = (start: string, end: string | null) => {
    if (!end) return isRunning ? 'running' : '-';
    const ms = new Date(end).getTime() - new Date(start).getTime();
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    const mins = Math.floor(ms / 60000);
    const secs = Math.floor((ms % 60000) / 1000);
    if (mins < 60) return `${mins}m ${secs}s`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}h ${mins % 60}m`;
  };

  const formatUptime = () => {
    if (!job.started_at) return null;
    const ms = Date.now() - new Date(job.started_at).getTime();
    const secs = Math.floor(ms / 1000);
    if (secs < 60) return `${secs}s`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ${secs % 60}s`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}h ${mins % 60}m`;
  };

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Link to="/jobs" className="text-text-muted hover:text-text-secondary text-sm transition-colors">&larr; Jobs</Link>
          </div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">{job.name}</h1>
          <div className="flex items-center gap-3 mt-2">
            <span className={`text-xs px-2 py-0.5 rounded-md border font-medium ${statusBadge[job.status] || statusBadge.stopped}`}>
              {isRunning && <span className="inline-block w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse" />}
              {job.status}
            </span>
            <span className="text-sm text-text-muted font-mono">{job.job_type.replace(/_/g, ' ')}</span>
            {job.pid && <span className="text-xs text-text-muted font-mono">PID {job.pid}</span>}
            {isRunning && formatUptime() && (
              <span className="text-xs text-text-muted font-mono">uptime {formatUptime()}</span>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <div className="flex gap-2">
            {!isRunning && (
              <>
                <button onClick={() => api.post(`/jobs/${jobId}/start`, { run_mode: 'full_load_cdc' }).then(() => queryClient.invalidateQueries({ queryKey: ['job', jobId] }))}
                  className="px-4 py-2 bg-status-running hover:bg-status-running/80 text-surface-0 rounded-md text-sm font-semibold transition-colors">
                  Full Load + CDC
                </button>
                <button onClick={() => api.post(`/jobs/${jobId}/start`, { run_mode: 'cdc' }).then(() => queryClient.invalidateQueries({ queryKey: ['job', jobId] }))}
                  className="px-4 py-2 bg-accent hover:bg-accent-hover text-surface-0 rounded-md text-sm font-semibold transition-colors">
                  Start CDC
                </button>
                <button onClick={() => api.post(`/jobs/${jobId}/start`, { run_mode: 'full_load' }).then(() => queryClient.invalidateQueries({ queryKey: ['job', jobId] }))}
                  className="px-4 py-2 bg-surface-3 hover:bg-surface-3/70 text-text-primary rounded-md text-sm font-medium transition-colors">
                  Full Load Only
                </button>
              </>
            )}
          </div>
          {!isRunning && (
            <span className="text-[11px] text-text-muted">Full loads truncate target tables before reloading</span>
          )}
          {isRunning && (
            <button onClick={() => actionMutation.mutate('stop')}
              className="px-4 py-2 bg-status-warning hover:bg-status-warning/80 text-surface-0 rounded-md text-sm font-semibold transition-colors">
              Stop
            </button>
          )}
        </div>
      </div>

      {/* Data Pipeline Flow */}
      <div className="bg-surface-1 border border-surface-3/50 rounded-lg p-6 mb-6">
        <div className="flex items-center justify-between">
          {/* Source endpoint */}
          <div className="flex-1">
            <div className={`rounded-lg p-4 border ${isRunning ? 'bg-accent/5 border-accent/30' : 'bg-surface-2/50 border-surface-3/50'}`}>
              <div className="flex items-center gap-3 mb-2">
                <div className={`w-10 h-10 rounded-md flex items-center justify-center ${isRunning ? 'bg-accent/15' : 'bg-surface-3/30'}`}>
                  <svg className={`w-5 h-5 ${isRunning ? 'text-accent' : 'text-text-muted'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                  </svg>
                </div>
                <div>
                  <div className="text-sm font-semibold text-text-primary">{sourceEp?.name || 'Source'}</div>
                  <div className="text-xs text-text-muted font-mono">
                    {sourceEp ? `${dbTypeLabel[sourceEp.db_type] || sourceEp.db_type} @ ${sourceEp.host}:${sourceEp.port}` : '...'}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Arrow */}
          <div className="w-16 flex flex-col items-center justify-center shrink-0 mx-2">
            <div className="relative w-full h-0.5">
              <div className="absolute inset-0 bg-surface-3" />
              {isRunning && (
                <div className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 bg-status-running rounded-full shadow-lg shadow-status-running/50"
                  style={{ animation: 'flowRight 1.5s linear infinite' }} />
              )}
            </div>
            {isRunning && m.rows_this_cycle > 0 && (
              <span className="text-[10px] text-status-running font-mono font-bold mt-1">+{m.rows_this_cycle}</span>
            )}
          </div>

          {/* CDC Engine */}
          <div className="shrink-0">
            <div className={`rounded-lg p-4 border text-center ${
              isRunning ? 'bg-status-running/5 border-status-running/30' : 'bg-surface-2/50 border-surface-3/50'
            }`}>
              <svg className={`w-8 h-8 mx-auto ${isRunning ? 'text-status-running animate-spin' : 'text-text-muted'}`}
                style={isRunning ? { animationDuration: '3s' } : {}}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <div className="text-xs text-text-muted mt-2 font-medium">CDC</div>
            </div>
          </div>

          {/* Arrow */}
          <div className="w-16 flex flex-col items-center justify-center shrink-0 mx-2">
            <div className="relative w-full h-0.5">
              <div className="absolute inset-0 bg-surface-3" />
              {isRunning && (
                <div className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 bg-status-running rounded-full shadow-lg shadow-status-running/50"
                  style={{ animation: 'flowRight 1.5s linear infinite', animationDelay: '0.75s' }} />
              )}
            </div>
          </div>

          {/* Target endpoint */}
          <div className="flex-1">
            <div className={`rounded-lg p-4 border ${isRunning ? 'bg-purple-500/5 border-purple-500/30' : 'bg-surface-2/50 border-surface-3/50'}`}>
              <div className="flex items-center gap-3 mb-2">
                <div className={`w-10 h-10 rounded-md flex items-center justify-center ${isRunning ? 'bg-purple-500/15' : 'bg-surface-3/30'}`}>
                  <svg className={`w-5 h-5 ${isRunning ? 'text-purple-400' : 'text-text-muted'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                  </svg>
                </div>
                <div>
                  <div className="text-sm font-semibold text-text-primary">{targetEp?.name || 'Target'}</div>
                  <div className="text-xs text-text-muted font-mono">
                    {targetEp ? `${dbTypeLabel[targetEp.db_type] || targetEp.db_type} @ ${targetEp.host}:${targetEp.port}` : '...'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Live Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <MetricCard label="Rows Total" value={m.rows_total.toLocaleString()} highlight={m.rows_total > 0} />
        <MetricCard label="This Cycle" value={String(m.rows_this_cycle)} highlight={m.rows_this_cycle > 0} />
        <MetricCard label="Checkpoint" value={String(m.checkpoint)} mono />
        <MetricCard label="Cycle" value={String(m.cycle)} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
        <MetricCard label="Cycle Duration" value={m.cycle_duration_ms != null ? `${m.cycle_duration_ms}ms` : '-'} mono />
        <MetricCard label="Est. Lag" value={m.lag_ms != null ? (m.lag_ms < 1000 ? `${m.lag_ms}ms` : `${(m.lag_ms / 1000).toFixed(1)}s`) : '-'} mono />
        <MetricCard label="Errors" value={String(m.errors)} error={m.errors > 0} />
      </div>

      {/* Per-table breakdown */}
      {m.by_table && Object.keys(m.by_table).length > 0 && (
        <div className="bg-surface-1 border border-surface-3/50 rounded-lg p-4 mb-6">
          <h3 className="text-sm font-semibold text-text-secondary mb-3">Per-Table Changes</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
            {Object.entries(m.by_table).map(([table, counts]: [string, any]) => (
              <div key={table} className="text-xs bg-surface-2 rounded-md p-2.5">
                <div className="text-text-primary font-medium font-mono truncate">{table}</div>
                <div className="text-text-muted mt-1 space-x-2">
                  <span className="text-status-running">+{counts.I}</span>
                  <span className="text-accent">~{counts.U}</span>
                  <span className="text-status-error">-{counts.D}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Log viewer */}
        <div className="bg-surface-1 border border-surface-3/50 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-text-secondary">Live Logs</h3>
            {isRunning && <span className="text-[10px] text-status-running font-mono animate-pulse">streaming</span>}
          </div>
          <div className="bg-surface-0 rounded-md p-3 h-56 overflow-auto font-mono text-xs text-text-muted leading-relaxed">
            {logsData?.lines?.length ? (
              logsData.lines.map((line, i) => (
                <div key={i} className={`flex gap-3 ${
                  line.includes('ERROR') ? 'text-status-error' :
                  line.includes('WARN') ? 'text-status-warning' : ''
                }`}>
                  <span className="text-text-muted/40 select-none w-6 text-right shrink-0">{i + 1}</span>
                  <span className="break-all">{line}</span>
                </div>
              ))
            ) : (
              <div className="text-text-muted/40 italic">No log output yet</div>
            )}
          </div>
        </div>

        {/* Job Configuration */}
        <div className="bg-surface-1 border border-surface-3/50 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-text-secondary mb-3">Configuration</h3>
          <div className="space-y-2 text-sm">
            <ConfigRow label="Job Type" value={job.job_type.replace(/_/g, ' ')} />
            <ConfigRow label="Poll Interval" value={`${job.poll_interval}s`} />
            <ConfigRow label="Batch Size" value={job.batch_size.toLocaleString()} />
            <ConfigRow label="Tables" value={job.table_list?.join(', ') || 'All tables'} />
            {job.heartbeat_at && (
              <ConfigRow label="Last Heartbeat" value={new Date(job.heartbeat_at).toLocaleTimeString()} />
            )}
          </div>
        </div>
      </div>

      {/* Run history */}
      <div className="bg-surface-1 border border-surface-3/50 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3/50 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-secondary">Run History</h3>
          <span className="text-xs text-text-muted">{runs.length} runs</span>
        </div>
        {runs.length === 0 ? (
          <p className="p-4 text-text-muted text-sm">No runs yet</p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-3/50 text-text-muted text-left uppercase tracking-wider">
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Started</th>
                <th className="px-4 py-2 font-medium">Duration</th>
                <th className="px-4 py-2 font-medium">Rows</th>
                <th className="px-4 py-2 font-medium">I/U/D</th>
                <th className="px-4 py-2 font-medium">Errors</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run, i) => (
                <tr key={run.id} className={`border-b border-surface-3/20 text-text-secondary ${i % 2 === 1 ? 'bg-surface-2/20' : ''}`}>
                  <td className="px-4 py-2 font-mono">{run.run_type}</td>
                  <td className="px-4 py-2">
                    <span className={`px-1.5 py-0.5 rounded-md border font-medium ${statusBadge[run.status] || ''}`}>
                      {run.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 font-mono">{new Date(run.started_at).toLocaleString()}</td>
                  <td className="px-4 py-2 font-mono">{formatDuration(run.started_at, run.ended_at)}</td>
                  <td className="px-4 py-2 font-mono">{run.rows_total.toLocaleString()}</td>
                  <td className="px-4 py-2 font-mono">
                    <span className="text-status-running">{run.rows_inserted}</span>
                    <span className="text-text-muted">/</span>
                    <span className="text-accent">{run.rows_updated}</span>
                    <span className="text-text-muted">/</span>
                    <span className="text-status-error">{run.rows_deleted}</span>
                  </td>
                  <td className="px-4 py-2 font-mono">{run.error_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, value, mono, highlight, error: isError }: {
  label: string; value: string; mono?: boolean; highlight?: boolean; error?: boolean;
}) {
  return (
    <div className={`bg-surface-1 border rounded-lg p-4 ${
      isError ? 'border-status-error/30' :
      highlight ? 'border-accent/30' :
      'border-surface-3/50'
    }`}>
      <div className={`text-xl font-bold tracking-tight ${
        isError ? 'text-status-error' :
        highlight ? 'text-accent' :
        'text-text-primary'
      } ${mono ? 'font-mono text-lg' : ''}`}>{value}</div>
      <div className="text-xs text-text-muted mt-1 font-medium">{label}</div>
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-surface-3/20 last:border-0">
      <span className="text-text-muted">{label}</span>
      <span className="text-text-primary font-mono text-xs">{value}</span>
    </div>
  );
}
