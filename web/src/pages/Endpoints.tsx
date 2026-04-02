import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';
import { useAuth } from '../auth/AuthContext';

interface Endpoint {
  id: number;
  name: string;
  db_type: string;
  host: string;
  port: number;
  database_name: string | null;
  schema_name: string | null;
  username: string;
}

const emptyForm = {
  name: '', db_type: 'sqlserver', host: '', port: 1433,
  database_name: '', schema_name: '', username: '', password: '',
  oracle_dsn: '', oracle_cdb_dsn: '', oracle_sys_password: '',
};

export default function Endpoints() {
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [editId, setEditId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [testResult, setTestResult] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const { data: endpoints = [], isLoading } = useQuery<Endpoint[]>({
    queryKey: ['endpoints'],
    queryFn: () => api.get('/endpoints'),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (editId) {
        return api.put(`/endpoints/${editId}`, form);
      }
      return api.post('/endpoints', form);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['endpoints'] });
      setShowForm(false);
      setForm(emptyForm);
      setEditId(null);
      setError('');
    },
    onError: (e: ApiError) => setError(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/endpoints/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['endpoints'] }),
  });

  const testMutation = useMutation({
    mutationFn: () => api.post<{ success: boolean; message: string; latency_ms: number | null }>('/endpoints/test', {
      db_type: form.db_type, host: form.host, port: form.port,
      username: form.username, password: form.password,
      database_name: form.database_name || null,
      oracle_dsn: form.oracle_dsn || null,
    }),
    onSuccess: (res: any) => {
      setTestResult(res.success ? `Connected (${res.latency_ms}ms)` : `Failed: ${res.message}`);
    },
    onError: (e: ApiError) => setTestResult(`Error: ${e.message}`),
  });

  const startEdit = (ep: Endpoint) => {
    setForm({
      ...emptyForm,
      name: ep.name,
      db_type: ep.db_type,
      host: ep.host,
      port: ep.port,
      database_name: ep.database_name || '',
      schema_name: ep.schema_name || '',
      username: ep.username,
      password: '',
    });
    setEditId(ep.id);
    setShowForm(true);
    setTestResult(null);
    setShowPassword(false);
  };

  const updateField = (field: string, value: string | number) => {
    if (field === 'db_type') {
      const ports: Record<string, number> = { sqlserver: 1433, oracle: 1521, postgresql: 5432 };
      setForm((prev) => ({ ...prev, db_type: String(value), port: ports[String(value)] || prev.port }));
    } else {
      setForm((prev) => ({ ...prev, [field]: value }));
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">Endpoints</h1>
        {isAdmin && (
          <button
            onClick={() => { setShowForm(true); setEditId(null); setForm(emptyForm); setTestResult(null); setShowPassword(false); }}
            className="px-4 py-2 bg-accent hover:bg-accent-hover text-surface-0 rounded-md text-sm font-semibold transition-colors"
          >
            + Add Endpoint
          </button>
        )}
      </div>

      {/* Form */}
      {showForm && (
        <div className="bg-surface-1 border border-surface-3/50 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-text-primary mb-4">
            {editId ? 'Edit Endpoint' : 'New Endpoint'}
          </h2>
          {error && <div className="mb-4 p-3 bg-status-error/10 border border-status-error/30 rounded-md text-status-error text-sm">{error}</div>}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Name</label>
              <input value={form.name} onChange={(e) => updateField('name', e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Type</label>
              <select value={form.db_type} onChange={(e) => updateField('db_type', e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors">
                <option value="sqlserver">SQL Server</option>
                <option value="oracle">Oracle</option>
                <option value="postgresql">PostgreSQL</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Host</label>
              <input value={form.host} onChange={(e) => updateField('host', e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Port</label>
              <input type="number" value={form.port} onChange={(e) => updateField('port', parseInt(e.target.value))}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Database / Service</label>
              <input value={form.database_name} onChange={(e) => updateField('database_name', e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Schema</label>
              <input value={form.schema_name} onChange={(e) => updateField('schema_name', e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Username</label>
              <input value={form.username} onChange={(e) => updateField('username', e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Password</label>
              <input type={showPassword ? 'text' : 'password'} value={form.password} onChange={(e) => updateField('password', e.target.value)}
                placeholder={editId ? '(unchanged)' : ''}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
              <label className="flex items-center gap-2 mt-1.5 cursor-pointer">
                <input type="checkbox" checked={showPassword} onChange={(e) => setShowPassword(e.target.checked)}
                  className="rounded border-surface-3 bg-surface-2 text-accent focus:ring-accent/40" />
                <span className="text-xs text-text-muted">Show password</span>
              </label>
            </div>
          </div>

          {/* Oracle-specific fields */}
          {form.db_type === 'oracle' && (
            <div className="mt-4 p-4 border border-dashed border-surface-3 rounded-md">
              <p className="text-xs text-text-muted font-medium mb-3 uppercase tracking-wider">Oracle-specific</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-text-secondary mb-1.5 font-medium">Oracle DSN (PDB)</label>
                  <input value={form.oracle_dsn} onChange={(e) => updateField('oracle_dsn', e.target.value)}
                    placeholder="host:port/service"
                    className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
                </div>
                <div>
                  <label className="block text-sm text-text-secondary mb-1.5 font-medium">Oracle CDB DSN</label>
                  <input value={form.oracle_cdb_dsn} onChange={(e) => updateField('oracle_cdb_dsn', e.target.value)}
                    className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
                </div>
              </div>
            </div>
          )}

          <div className="flex items-center gap-3 mt-5">
            <button onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="px-4 py-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-surface-0 rounded-md text-sm font-semibold transition-colors">
              {saveMutation.isPending ? 'Saving...' : 'Save'}
            </button>
            <button onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending}
              className="px-4 py-2 bg-surface-3 hover:bg-surface-3/70 text-text-primary rounded-md text-sm font-medium transition-colors">
              {testMutation.isPending ? 'Testing...' : 'Test Connection'}
            </button>
            <button onClick={() => { setShowForm(false); setError(''); }}
              className="px-4 py-2 text-text-muted hover:text-text-primary text-sm transition-colors">
              Cancel
            </button>
            {testResult && (
              <span className={`text-sm font-medium ${testResult.startsWith('Connected') ? 'text-status-running' : 'text-status-error'}`}>
                {testResult}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <p className="text-text-muted">Loading...</p>
      ) : (
        <div className="bg-surface-1 border border-surface-3/50 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3/50 text-text-muted text-left text-xs uppercase tracking-wider">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Host</th>
                <th className="px-4 py-3 font-medium">Port</th>
                <th className="px-4 py-3 font-medium">Database</th>
                <th className="px-4 py-3 font-medium">User</th>
                {isAdmin && <th className="px-4 py-3 font-medium">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {endpoints.map((ep, i) => (
                <tr key={ep.id} className={`border-b border-surface-3/30 text-text-secondary hover:bg-surface-2/50 transition-colors ${i % 2 === 1 ? 'bg-surface-2/20' : ''}`}>
                  <td className="px-4 py-3 font-medium text-text-primary">{ep.name}</td>
                  <td className="px-4 py-3 font-mono text-xs">{ep.db_type}</td>
                  <td className="px-4 py-3 font-mono text-xs">{ep.host}</td>
                  <td className="px-4 py-3 font-mono text-xs">{ep.port}</td>
                  <td className="px-4 py-3 font-mono text-xs">{ep.database_name || '-'}</td>
                  <td className="px-4 py-3 font-mono text-xs">{ep.username}</td>
                  {isAdmin && (
                    <td className="px-4 py-3 space-x-3">
                      <button onClick={() => startEdit(ep)} className="text-accent hover:text-accent-hover text-xs font-medium transition-colors">Edit</button>
                      <button onClick={() => { if (confirm('Delete this endpoint?')) deleteMutation.mutate(ep.id); }}
                        className="text-status-error hover:text-status-error/80 text-xs font-medium transition-colors">Delete</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
