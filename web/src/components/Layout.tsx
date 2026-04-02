import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import ThemeToggle from './ThemeToggle';
import ChangePasswordDialog from './ChangePasswordDialog';

const navItems = [
  { to: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { to: '/endpoints', label: 'Endpoints', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2' },
  { to: '/jobs', label: 'Jobs', icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15' },
  { to: '/users', label: 'Users', icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z', adminOnly: true },
  { to: '/audit', label: 'Audit Log', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2', adminOnly: true },
];

export default function Layout() {
  const { user, logout, isAdmin } = useAuth();
  const [showChangePassword, setShowChangePassword] = useState(false);

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary flex">
      {/* Sidebar */}
      <aside className="w-60 bg-surface-1 border-r border-surface-3/50 flex flex-col shrink-0">
        <div className="p-4 border-b border-surface-3/50">
          <h1 className="text-lg font-bold text-text-primary tracking-tight">Dude Replicate</h1>
          <p className="text-xs text-text-muted mt-0.5 font-mono">CDC Management</p>
        </div>

        <nav className="flex-1 p-3 space-y-0.5">
          {navItems
            .filter((item) => !item.adminOnly || isAdmin)
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive
                      ? 'bg-accent-muted text-accent border-l-2 border-accent font-medium'
                      : 'text-text-secondary hover:text-text-primary hover:bg-surface-2'
                  }`
                }
              >
                <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                </svg>
                {item.label}
              </NavLink>
            ))}
        </nav>

        <div className="p-3 border-t border-surface-3/50 space-y-1">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm truncate">
              <div className="text-text-primary font-medium">{user?.display_name}</div>
              <div className="text-xs text-text-muted">{user?.role.replace('dude_replicate_', '')}</div>
            </div>
            <ThemeToggle />
          </div>
          <button
            onClick={() => setShowChangePassword(true)}
            className="w-full px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-2 rounded-md transition-colors text-left"
          >
            Change Password
          </button>
          <button
            onClick={logout}
            className="w-full px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-2 rounded-md transition-colors text-left"
          >
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main content — centered with max-width for balance */}
      <main className="flex-1 p-8 overflow-auto">
        <div className="max-w-6xl mx-auto">
          <Outlet />
        </div>
      </main>

      {/* Change Password Dialog */}
      <ChangePasswordDialog open={showChangePassword} onClose={() => setShowChangePassword(false)} />
    </div>
  );
}
