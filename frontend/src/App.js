import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider } from './context/AuthContext';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import UploadPage from './pages/UploadPage';
import HistoryPage from './pages/HistoryPage';
import Navbar from './components/Navbar';

const AppLayout = ({ children }) => (
  <div className="min-h-screen bg-dark-950 grid-bg relative">
    <Navbar />
    <main className="max-w-7xl mx-auto px-4 sm:px-6 pt-5 pb-16 relative z-10">
      {children}
    </main>
  </div>
);

const App = () => (
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
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/dashboard" element={<AppLayout><Dashboard /></AppLayout>} />
        <Route path="/upload" element={<AppLayout><UploadPage /></AppLayout>} />
        <Route path="/history" element={<AppLayout><HistoryPage /></AppLayout>} />
        <Route path="/login" element={<Navigate to="/dashboard" />} />
        <Route path="/register" element={<Navigate to="/dashboard" />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  </AuthProvider>
);

export default App;
