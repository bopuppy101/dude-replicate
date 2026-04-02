import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';

interface User {
  id: number; email: string; display_name: string; role: string; is_active: boolean;
}

const emptyForm = { email: '', password: '', display_name: '', role: 'dude_replicate_operator' };

export default function Users() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => api.get('/users'),
  });

  const createMutation = useMutation({
    mutationFn: () => api.post('/users', form),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['users'] }); setShowForm(false); setForm(emptyForm); },
    onError: (e: ApiError) => setError(e.message),
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/users/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">Users</h1>
        <button onClick={() => { setShowForm(true); setForm(emptyForm); setError(''); }}
          className="px-4 py-2 bg-accent hover:bg-accent-hover text-surface-0 rounded-md text-sm font-semibold transition-colors">
          + Add User
        </button>
      </div>

      {showForm && (
        <div className="bg-surface-1 border border-surface-3/50 rounded-lg p-6 mb-6">
          <h2 className="text-lg font-semibold text-text-primary mb-4">New User</h2>
          {error && <div className="mb-4 p-3 bg-status-error/10 border border-status-error/30 rounded-md text-status-error text-sm">{error}</div>}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Email</label>
              <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Display Name</label>
              <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Password</label>
              <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5 font-medium">Role</label>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full px-3 py-2 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors">
                <option value="dude_replicate_operator">Operator</option>
                <option value="dude_replicate_admin">Admin</option>
              </select>
            </div>
          </div>
          <div className="flex gap-3 mt-5">
            <button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}
              className="px-4 py-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-surface-0 rounded-md text-sm font-semibold transition-colors">
              {createMutation.isPending ? 'Creating...' : 'Create User'}
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 text-text-muted hover:text-text-primary text-sm transition-colors">Cancel</button>
          </div>
        </div>
      )}

      {isLoading ? <p className="text-text-muted">Loading...</p> : (
        <div className="bg-surface-1 border border-surface-3/50 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3/50 text-text-muted text-left text-xs uppercase tracking-wider">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u, i) => (
                <tr key={u.id} className={`border-b border-surface-3/30 text-text-secondary hover:bg-surface-2/50 transition-colors ${i % 2 === 1 ? 'bg-surface-2/20' : ''}`}>
                  <td className="px-4 py-3 text-text-primary font-medium">{u.display_name}</td>
                  <td className="px-4 py-3 font-mono text-xs">{u.email}</td>
                  <td className="px-4 py-3">{u.role.replace('dude_replicate_', '')}</td>
                  <td className="px-4 py-3">
                    <span className={u.is_active
                      ? 'text-xs px-2 py-0.5 rounded-md border bg-status-running/15 text-status-running border-status-running/30 font-medium'
                      : 'text-xs px-2 py-0.5 rounded-md border bg-status-error/15 text-status-error border-status-error/30 font-medium'}>
                      {u.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active && (
                      <button onClick={() => { if (confirm('Deactivate this user?')) deactivateMutation.mutate(u.id); }}
                        className="text-status-error hover:text-status-error/80 text-xs font-medium transition-colors">Deactivate</button>
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
