import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, Upload, History, LogOut, Sparkles, User, Shield,
  Menu, X, ChevronDown
} from 'lucide-react';

const Navbar = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/upload', label: 'Upload', icon: Upload },
    { path: '/history', label: 'History', icon: History },
  ];

  const isActive = (path) => location.pathname === path;

  return (
    <motion.nav
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="sticky top-0 z-50 bg-dark-950/95 border-b border-dark-700/30 px-4 sm:px-6 py-3.5 backdrop-blur-md"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        {/* Logo */}
        <Link to="/dashboard" className="flex items-center gap-2 group">
          <div className="w-9 h-9 rounded-lg bg-dark-900 border border-primary-500/30 flex items-center justify-center shadow-md shadow-primary-500/5 group-hover:border-primary-500/80 transition-all duration-300">
            <Sparkles className="w-5 h-5 text-primary-500 animate-pulse" />
          </div>
          <div className="hidden sm:block">
            <h1 className="text-xl font-black tracking-tighter text-white uppercase select-none">
              GenAI<span className="text-primary-500">BI</span>
            </h1>
            <p className="text-[9px] text-dark-500 -mt-1 font-semibold tracking-widest uppercase">Intelligence</p>
          </div>
        </Link>

        {/* Desktop Navigation */}
        <div className="hidden md:flex items-center gap-2">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-bold transition-all duration-200 ${
                isActive(item.path)
                  ? 'bg-primary-500/10 text-primary-500 border-b-2 border-primary-500 rounded-b-none'
                  : 'text-dark-300 hover:text-white hover:bg-dark-800/40'
              }`}
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </Link>
          ))}
        </div>

        {/* User Menu */}
        <div className="flex items-center gap-3">
          {/* User pill */}
          <div className="relative hidden sm:block">
            <button
              onClick={() => setProfileOpen(!profileOpen)}
              className="flex items-center gap-2 px-3 py-2 min-h-[44px] rounded-lg bg-dark-800/80 border border-dark-700 hover:border-dark-600 transition-colors"
            >
              {user?.role === 'admin' ? (
                <Shield className="w-4 h-4 text-amber-400" />
              ) : (
                <User className="w-4 h-4 text-primary-400" />
              )}
              <span className="text-sm text-dark-300">{user?.username || 'User'}</span>
              <ChevronDown className={`w-3 h-3 text-dark-500 transition-transform ${profileOpen ? 'rotate-180' : ''}`} />
            </button>

            <AnimatePresence>
              {profileOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -5, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -5, scale: 0.95 }}
                  className="absolute right-0 mt-2 w-48 bg-dark-800 border border-dark-700 rounded-xl shadow-2xl overflow-hidden"
                >
                  <div className="p-3 border-b border-dark-700">
                    <p className="text-sm text-dark-200 font-medium">{user?.username}</p>
                    <p className="text-xs text-dark-500">{user?.email}</p>
                    <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded bg-dark-700 text-dark-400 uppercase tracking-wider">
                      {user?.role}
                    </span>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-3 text-sm text-dark-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign Out
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Logout icon on desktop */}
          <button
            onClick={handleLogout}
            className="hidden sm:flex items-center justify-center gap-2 w-11 h-11 px-3 py-2 rounded-xl text-dark-400 hover:text-red-400 hover:bg-red-500/10 transition-all duration-300"
            title="Sign out"
          >
            <LogOut className="w-4 h-4" />
          </button>

          {/* Mobile menu button */}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden w-11 h-11 flex items-center justify-center rounded-xl text-dark-400 hover:text-dark-200 hover:bg-dark-700/50 transition-colors"
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Navigation */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="md:hidden mt-3 pt-3 border-t border-dark-700/50 overflow-hidden"
          >
            <div className="space-y-1">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileOpen(false)}
                  className={`min-h-[44px] flex items-center gap-3 px-4 py-3 rounded-md text-sm font-bold transition-all ${
                    isActive(item.path)
                      ? 'bg-primary-500/10 text-primary-500'
                      : 'text-dark-300 hover:text-white hover:bg-dark-800/40'
                  }`}
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </Link>
              ))}
              <button
                onClick={handleLogout}
                className="w-full min-h-[44px] flex items-center gap-3 px-4 py-3 rounded-md text-sm font-medium text-dark-400 hover:text-red-400 hover:bg-red-500/10 transition-all"
              >
                <LogOut className="w-4 h-4" />
                Sign Out
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
};

export default Navbar;
