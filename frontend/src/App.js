import React, { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import ErrorBoundary from './components/ErrorBoundary';
import FullPageLoader from './components/FullPageLoader';
import Navbar from './components/Navbar';

const Landing = lazy(() => import('./pages/Landing'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const VerifyEmail = lazy(() => import('./pages/VerifyEmail'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const UploadPage = lazy(() => import('./pages/UploadPage'));
const HistoryPage = lazy(() => import('./pages/HistoryPage'));

const AppLayout = ({ children }) => (
  <div className="min-h-screen bg-dark-950 grid-bg relative">
    <Navbar />
    <main className="max-w-7xl mx-auto px-4 sm:px-6 pt-5 pb-16 relative z-10">{children}</main>
  </div>
);

const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullPageLoader />;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
};

const PublicOnlyRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return <FullPageLoader />;
  if (user) return <Navigate to="/dashboard" replace />;
  return children;
};

const App = () => (
  <ErrorBoundary>
    <AuthProvider>
      <Router>
        <Toaster
          position="top-center"
          toastOptions={{
            style: {
              background: '#2c2c2e',
              color: '#e8e8ed',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '10px',
              fontSize: '14px',
              fontFamily: 'Inter, -apple-system, sans-serif',
            },
            success: { iconTheme: { primary: '#34c759', secondary: '#1c1c1e' } },
            error: { iconTheme: { primary: '#ff3b30', secondary: '#1c1c1e' } },
          }}
        />
        <Suspense fallback={<FullPageLoader />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route
              path="/login"
              element={
                <PublicOnlyRoute>
                  <Login />
                </PublicOnlyRoute>
              }
            />
            <Route
              path="/register"
              element={
                <PublicOnlyRoute>
                  <Register />
                </PublicOnlyRoute>
              }
            />
            <Route
              path="/forgot-password"
              element={
                <PublicOnlyRoute>
                  <ForgotPassword />
                </PublicOnlyRoute>
              }
            />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Dashboard />
                  </AppLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/upload"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <UploadPage />
                  </AppLayout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/history"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <HistoryPage />
                  </AppLayout>
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Router>
    </AuthProvider>
  </ErrorBoundary>
);

export default App;
