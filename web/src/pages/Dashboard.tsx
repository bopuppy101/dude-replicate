import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { Link } from 'react-router-dom';

interface Job {
  id: number;
  name: string;
  status: string;
  job_type: string;
  source_endpoint_id: number;
  target_endpoint_id: number;
  started_at: string | null;
  live_metrics: Record<string, unknown> | null;
}

interface Endpoint { id: number; name: string; db_type: string; }

const statusDot: Record<string, string> = {
  running: 'bg-status-running',
  stopped: 'bg-status-warning',
  error: 'bg-status-error',
  stopping: 'bg-status-warning',
};

const statusBadge: Record<string, string> = {
  running: 'bg-status-running/15 text-status-running border-status-running/30',
  stopped: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  error: 'bg-status-error/15 text-status-error border-status-error/30',
  stopping: 'bg-status-warning/15 text-status-warning border-status-warning/30',
};

export default function Dashboard() {
  const { data: jobs = [], isLoading } = useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => api.get('/jobs'),
    refetchInterval: 5000,
  });

  const { data: endpoints = [] } = useQuery<Endpoint[]>({
    queryKey: ['endpoints'],
    queryFn: () => api.get('/endpoints'),
  });

  const running = jobs.filter((j) => j.status === 'running').length;
  const stopped = jobs.filter((j) => j.status === 'stopped').length;
  const errors = jobs.filter((j) => j.status === 'error').length;
  const totalRows = jobs.reduce((sum, j) => {
    const m = j.live_metrics as { rows_total?: number } | null;
    return sum + (m?.rows_total || 0);
  }, 0);

  const endpointName = (id: number) => endpoints.find((e) => e.id === id)?.name || `#${id}`;

  return (
    <div>
      <h1 className="text-2xl font-bold text-text-primary mb-8 tracking-tight">Dashboard</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
        <StatCard value={running} label="Running" color="border-status-running" valueColor="text-status-running" />
        <StatCard value={stopped} label="Stopped" color="border-status-warning" valueColor="text-status-warning" />
        <StatCard value={errors} label="Errors" color="border-status-error" valueColor="text-status-error" />
        <StatCard value={totalRows.toLocaleString()} label="Rows Replicated" color="border-accent" valueColor="text-accent" />
      </div>

      {/* Job list */}
      <h2 className="text-lg font-semibold text-text-primary mb-4 tracking-tight">Replication Jobs</h2>
      {isLoading ? (
        <p className="text-text-muted">Loading...</p>
      ) : jobs.length === 0 ? (
        <p className="text-text-muted">No jobs configured yet.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {jobs.map((job) => (
            <Link
              key={job.id}
              to={`/jobs/${job.id}`}
              className="bg-surface-1 border border-surface-3/50 rounded-lg p-5 hover:border-accent/40 hover:bg-surface-2/50 transition-all group"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <span className={`w-2.5 h-2.5 rounded-full ${statusDot[job.status] || statusDot.stopped} ${
                    job.status === 'running' ? 'animate-pulse' : ''
                  }`} />
                  <span className="font-semibold text-text-primary group-hover:text-accent transition-colors">
                    {job.name}
                  </span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-md border font-medium ${statusBadge[job.status] || statusBadge.stopped}`}>
                  {job.status}
                </span>
              </div>
              <div className="flex items-center gap-2 text-sm text-text-secondary">
                <span className="font-mono text-xs">{endpointName(job.source_endpoint_id)}</span>
                <span className="text-text-muted">&rarr;</span>
                <span className="font-mono text-xs">{endpointName(job.target_endpoint_id)}</span>
              </div>
              <div className="text-xs text-text-muted mt-2">
                {job.job_type.replace(/_/g, ' ')}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function StatCard({ value, label, color, valueColor }: { value: number | string; label: string; color: string; valueColor: string }) {
  return (
    <div className={`bg-surface-1 border border-surface-3/50 rounded-lg p-5 border-l-4 ${color}`}>
      <div className={`text-3xl font-bold ${valueColor} tracking-tight`}>{value}</div>
      <div className="text-sm text-text-muted mt-1 font-medium">{label}</div>
    </div>
  );
}
