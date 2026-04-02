import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

interface AuditEntry {
  id: number; user_email: string | null; action: string;
  resource_type: string | null; resource_id: number | null;
  detail: Record<string, unknown> | null; created_at: string;
}

interface AuditResponse {
  total: number; offset: number; limit: number; entries: AuditEntry[];
}

export default function AuditLog() {
  const [page, setPage] = useState(0);
  const limit = 25;

  const { data, isLoading } = useQuery<AuditResponse>({
    queryKey: ['audit', page],
    queryFn: () => api.get(`/audit-log?limit=${limit}&offset=${page * limit}`),
  });

  const entries = data?.entries || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / limit);

  return (
    <div>
      <h1 className="text-2xl font-bold text-text-primary mb-8 tracking-tight">Audit Log</h1>

      {isLoading ? <p className="text-text-muted">Loading...</p> : (
        <>
          <div className="bg-surface-1 border border-surface-3/50 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-3/50 text-text-muted text-left text-xs uppercase tracking-wider">
                  <th className="px-4 py-3 font-medium">Time</th>
                  <th className="px-4 py-3 font-medium">User</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                  <th className="px-4 py-3 font-medium">Resource</th>
                  <th className="px-4 py-3 font-medium">Details</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => (
                  <tr key={e.id} className={`border-b border-surface-3/30 text-text-secondary hover:bg-surface-2/50 transition-colors ${i % 2 === 1 ? 'bg-surface-2/20' : ''}`}>
                    <td className="px-4 py-2 text-xs whitespace-nowrap font-mono">
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-xs">{e.user_email || '-'}</td>
                    <td className="px-4 py-2 text-xs font-mono text-text-primary font-medium">{e.action}</td>
                    <td className="px-4 py-2 text-xs">
                      {e.resource_type ? `${e.resource_type} #${e.resource_id}` : '-'}
                    </td>
                    <td className="px-4 py-2 text-xs max-w-xs truncate text-text-muted font-mono">
                      {e.detail ? JSON.stringify(e.detail) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <span className="text-sm text-text-muted">{total} entries</span>
              <div className="flex gap-2">
                <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
                  className="px-3 py-1.5 text-sm bg-surface-2 text-text-secondary rounded-md hover:bg-surface-3 disabled:opacity-50 transition-colors">
                  Previous
                </button>
                <span className="px-3 py-1.5 text-sm text-text-muted font-mono">
                  {page + 1} / {totalPages}
                </span>
                <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
                  className="px-3 py-1.5 text-sm bg-surface-2 text-text-secondary rounded-md hover:bg-surface-3 disabled:opacity-50 transition-colors">
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
