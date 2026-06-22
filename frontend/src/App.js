import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider } from './context/AuthContext';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import UploadPage from './pages/UploadPage';
import HistoryPage from './pages/HistoryPage';
import Navbar from './components/Navbar';

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
        {/* Public Routes */}
        <Route path="/" element={<Landing />} />
        <Route path="/dashboard" element={<AppLayout><Dashboard /></AppLayout>} />
        <Route path="/upload" element={<AppLayout><UploadPage /></AppLayout>} />
        <Route path="/history" element={<AppLayout><HistoryPage /></AppLayout>} />

        {/* Catch-all & Auth redirects to dashboard */}
        <Route path="/login" element={<Navigate to="/dashboard" />} />
        <Route path="/register" element={<Navigate to="/dashboard" />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  </AuthProvider>
);

export default App;
