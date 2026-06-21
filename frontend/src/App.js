import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import UploadPage from './pages/UploadPage';
import HistoryPage from './pages/HistoryPage';
import Navbar from './components/Navbar';

/* Private route wrapper */
const PrivateRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-dark-950">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
          <p className="text-dark-400 text-sm">Loading...</p>
        </div>
      </div>
    );
  }
  return user ? children : <Navigate to="/login" />;
};

/* Public-only route (redirects logged-in users) */
const PublicRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return null;
  return user ? <Navigate to="/dashboard" /> : children;
};

/* Layout with Navbar */
const AppLayout = ({ children }) => (
  <div className="min-h-screen bg-dark-950 grid-bg relative">
    <Navbar />
    <main className="max-w-7xl mx-auto px-4 sm:px-6 pt-6 pb-16 relative z-10">
      {children}
    </main>
  </div>
);

const App = () => (
  <AuthProvider>
    <Router>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#1e293b',
            color: '#e2e8f0',
            border: '1px solid #334155',
            borderRadius: '12px',
          },
          success: { iconTheme: { primary: '#34d399', secondary: '#0f172a' } },
          error: { iconTheme: { primary: '#f87171', secondary: '#0f172a' } },
        }}
      />
      <Routes>
        {/* Public */}
        <Route path="/" element={<PublicRoute><Landing /></PublicRoute>} />
        <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
        <Route path="/register" element={<PublicRoute><Register /></PublicRoute>} />

        {/* Private */}
        <Route path="/dashboard" element={<PrivateRoute><AppLayout><Dashboard /></AppLayout></PrivateRoute>} />
        <Route path="/upload" element={<PrivateRoute><AppLayout><UploadPage /></AppLayout></PrivateRoute>} />
        <Route path="/history" element={<PrivateRoute><AppLayout><HistoryPage /></AppLayout></PrivateRoute>} />

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  </AuthProvider>
);

export default App;
