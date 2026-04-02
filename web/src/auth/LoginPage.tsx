import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err: any) {
      // Don't clear fields — let the user correct and retry
      setError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-0">
      <div className="w-full max-w-md p-8 bg-surface-1 rounded-xl border border-surface-3/50 shadow-2xl shadow-black/50">
        {/* Brand */}
        <div className="border-t-2 border-accent -mt-8 pt-8 -mx-8 px-8 rounded-t-xl">
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Dude Replicate</h1>
          <p className="text-sm font-mono text-accent mt-1">CDC Management Console</p>
          <p className="text-xs text-text-muted mt-1">SQL Server &amp; Oracle &rarr; PostgreSQL</p>
        </div>

        {error && (
          <div className="mt-6 p-3 bg-status-error/10 border border-status-error/30 rounded-md text-status-error text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 mt-6">
          <div>
            <label className="block text-sm text-text-secondary mb-1.5 font-medium">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2.5 bg-surface-2 border border-surface-3 rounded-md text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
              placeholder="admin@example.com"
            />
          </div>
          <div>
            <label className="block text-sm text-text-secondary mb-1.5 font-medium">Password</label>
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-3 py-2.5 bg-surface-2 border border-surface-3 rounded-md text-text-primary focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
            />
            <label className="flex items-center gap-2 mt-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showPassword}
                onChange={(e) => setShowPassword(e.target.checked)}
                className="rounded border-surface-3 bg-surface-2 text-accent focus:ring-accent/40"
              />
              <span className="text-sm text-text-muted">Show password</span>
            </label>
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-surface-0 rounded-md font-semibold transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p className="text-center text-xs text-text-muted mt-6">by DBDude Inc</p>
      </div>
    </div>
  );
}
