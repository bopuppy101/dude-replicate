import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import { useAuth } from '../auth/AuthContext';

interface Job {
  id: number; name: string; source_endpoint_id: number; target_endpoint_id: number;
  job_type: string; table_list: string[] | null; batch_size: number;
  status: string; pid: number | null; started_at: string | null;
  current_run_id: number | null; heartbeat_at: string | null;
  checkpoint: string | null; live_metrics: Record<string, unknown> | null;
}

interface Endpoint { id: number; name: string; db_type: string; }

const statusBadge: Record<string, string> = {
  running: 'bg-status-running/15 text-status-running border-status-running/30',
  stopped: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  error: 'bg-status-error/15 text-status-error border-status-error/30',
  stopping: 'bg-status-warning/15 text-status-warning border-status-warning/30',
};

const emptyForm = {
  name: '', source_endpoint_id: 0, target_endpoint_id: 0,
  job_type: 'cdc', table_list: '', batch_size: 1000,
};

export default function Jobs() {
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');

  const { data: jobs = [], isLoading } = useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => api.get('/jobs'),
    refetchInterval: 5000,
  });

  const { data: endpoints = [] } = useQuery<Endpoint[]>({
    queryKey: ['endpoints'],
    queryFn: () => api.get('/endpoints'),
  });

  const createMutation = useMutation({
    mutationFn: () => api.post('/jobs', {
      ...form,
      table_list: form.table_list ? form.table_list.split(',').map((t) => t.trim()).filter(Boolean) : null,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      setShowForm(false);
      setForm(emptyForm);
    },
    onError: (e: ApiError) => setError(e.message),
  });

  const actionMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) => api.post(`/jobs/${id}/${action}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/jobs/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  });

  const endpointName = (id: number) => endpoints.find((e) => e.id === id)?.name || `#${id}`;

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">Jobs</h1>
        {isAdmin && (
          <button onClick={() => { setShowForm(true); setForm(emptyForm); setError(''); }}
            className="px-4 py-2 bg-accent hover:bg-accent-hover text-surface-0 rounded-md text-sm font-semibold transition-colors">
            + New Job
          </button>
        )}
      </div>

      {/* Create form */}
      {showForm && isAdmin && (
        <div className="bg-surface-1 border border-surface-3/50 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-text-primary mb-4">New Job</h2>
          {error && <div className="mb-4 p-3 bg-status-error/10 border border-status-error/30 rounded-md text-status-error text-sm">{error}</div>}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Name</label>
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Type</label>
              <select value={form.job_type} onChange={(e) => setForm({ ...form, job_type: e.target.value })}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors">
                <option value="cdc">CDC</option>
                <option value="full_load">Full Load</option>
                <option value="full_load_cdc">Full Load + CDC</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Source Endpoint</label>
              <select value={form.source_endpoint_id} onChange={(e) => setForm({ ...form, source_endpoint_id: parseInt(e.target.value) })}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors">
                <option value={0}>Select...</option>
                {endpoints.map((ep) => <option key={ep.id} value={ep.id}>{ep.name} ({ep.db_type})</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Target Endpoint</label>
              <select value={form.target_endpoint_id} onChange={(e) => setForm({ ...form, target_endpoint_id: parseInt(e.target.value) })}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors">
                <option value={0}>Select...</option>
                {endpoints.map((ep) => <option key={ep.id} value={ep.id}>{ep.name} ({ep.db_type})</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Tables (comma-separated, blank = all)</label>
              <input value={form.table_list} onChange={(e) => setForm({ ...form, table_list: e.target.value })}
                placeholder="Customers, Orders, Products"
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
          </div>

          <div className="flex gap-3 mt-5">
            <button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}
              className="px-4 py-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-surface-0 rounded-md text-sm font-semibold transition-colors">
              {createMutation.isPending ? 'Creating...' : 'Create Job'}
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-text-muted hover:text-text-primary text-sm transition-colors">Cancel</button>
          </div>
        </div>
      )}

      {/* Jobs table */}
      {isLoading ? (
        <p className="text-text-muted">Loading...</p>
      ) : (
        <div className="bg-surface-1 border border-surface-3/50 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3/50 text-text-muted text-left text-xs uppercase tracking-wider">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Target</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-b border-surface-3/30 text-text-secondary hover:bg-surface-2/50 transition-colors">
                  <td className="px-4 py-3">
                    <Link to={`/jobs/${job.id}`} className="font-medium text-accent hover:text-accent-hover transition-colors">
                      {job.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{job.job_type.replace(/_/g, ' ')}</td>
                  <td className="px-4 py-3">{endpointName(job.source_endpoint_id)}</td>
                  <td className="px-4 py-3">{endpointName(job.target_endpoint_id)}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-md border font-medium ${statusBadge[job.status] || statusBadge.stopped}`}>
                      {job.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 space-x-3">
                    {job.status !== 'running' && (
                      <button onClick={() => api.post(`/jobs/${job.id}/start`, { run_mode: 'full_load_cdc' }).then(() => queryClient.invalidateQueries({ queryKey: ['jobs'] }))}
                        className="text-status-running hover:text-status-running/80 text-xs font-medium transition-colors">FL+CDC</button>
                    )}
                    {job.status !== 'running' && (
                      <button onClick={() => api.post(`/jobs/${job.id}/start`, { run_mode: 'cdc' }).then(() => queryClient.invalidateQueries({ queryKey: ['jobs'] }))}
                        className="text-accent hover:text-accent-hover text-xs font-medium transition-colors">CDC</button>
                    )}
                    {job.status === 'running' && (
                      <button onClick={() => actionMutation.mutate({ id: job.id, action: 'stop' })}
                        className="text-status-warning hover:text-status-warning/80 text-xs font-medium transition-colors">Stop</button>
                    )}
                    {isAdmin && job.status !== 'running' && (
                      <button onClick={() => { if (confirm('Delete this job?')) deleteMutation.mutate(job.id); }}
                        className="text-status-error hover:text-status-error/80 text-xs font-medium transition-colors">Delete</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
