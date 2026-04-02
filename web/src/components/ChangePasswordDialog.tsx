import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../api/client';

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function ChangePasswordDialog({ open, onClose }: Props) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPasswords, setShowPasswords] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  const reset = () => {
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setError('');
    setSuccess('');
    setShowPasswords(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('New passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/reset-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setSuccess('Password updated successfully.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to update password.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={handleClose} />

      {/* Dialog */}
      <div className="relative w-full max-w-md bg-surface-1 border border-surface-3/50 rounded-xl shadow-2xl shadow-black/50 p-6">
        <h2 className="text-lg font-bold text-text-primary mb-4">Change Password</h2>

        {error && (
          <div className="mb-4 p-3 bg-status-error/10 border border-status-error/30 rounded-md text-status-error text-sm">
            {error}
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 bg-status-running/10 border border-status-running/30 rounded-md text-status-running text-sm">
            {success}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-text-secondary mb-1.5 font-medium">Current Password</label>
            <input
              type={showPasswords ? 'text' : 'password'}
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="w-full px-3 py-2.5 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="block text-sm text-text-secondary mb-1.5 font-medium">New Password</label>
            <input
              type={showPasswords ? 'text' : 'password'}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              className="w-full px-3 py-2.5 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="block text-sm text-text-secondary mb-1.5 font-medium">Confirm New Password</label>
            <input
              type={showPasswords ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full px-3 py-2.5 bg-surface-2 border border-surface-3 rounded-md text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent transition-colors"
            />
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showPasswords}
              onChange={(e) => setShowPasswords(e.target.checked)}
              className="rounded border-surface-3 bg-surface-2 text-accent focus:ring-accent/40"
            />
            <span className="text-sm text-text-muted">Show passwords</span>
          </label>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-surface-0 rounded-md text-sm font-semibold transition-colors"
            >
              {loading ? 'Updating...' : 'Update Password'}
            </button>
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2.5 text-text-muted hover:text-text-primary text-sm transition-colors"
            >
              {success ? 'Close' : 'Cancel'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
