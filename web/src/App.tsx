import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './auth/AuthContext';
import ProtectedRoute from './auth/ProtectedRoute';
import Layout from './components/Layout';
import LoginPage from './auth/LoginPage';
import Dashboard from './pages/Dashboard';
import Endpoints from './pages/Endpoints';
import Jobs from './pages/Jobs';
import JobDetail from './pages/JobDetail';
import Users from './pages/Users';
import AuditLog from './pages/AuditLog';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5000 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<Dashboard />} />
              <Route path="/endpoints" element={<Endpoints />} />
              <Route path="/jobs" element={<Jobs />} />
              <Route path="/jobs/:id" element={<JobDetail />} />
              <Route path="/users" element={<Users />} />
              <Route path="/audit" element={<AuditLog />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
