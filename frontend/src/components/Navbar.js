import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, Upload, History, Sparkles,
  Menu, X, LogOut, ChevronDown, UserCircle, Table2
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const Navbar = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/explorer', label: 'Data Explorer', icon: Table2 },
    { path: '/upload', label: 'Upload', icon: Upload },
    { path: '/history', label: 'History', icon: History },
  ];

  const isActive = (path) => location.pathname === path;

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const displayName = user?.username || 'User';
  const initial = displayName.charAt(0).toUpperCase();

  return (
    <motion.nav
      initial={{ y: -16, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="sticky top-0 z-50 bg-dark-950/80 border-b border-white/[0.05] px-4 sm:px-6 py-3 backdrop-blur-4xl"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <Link to="/dashboard" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-apple bg-dark-800 border border-primary-500/20 flex items-center justify-center group-hover:border-primary-500/50 transition-all duration-300">
            <Sparkles className="w-4 h-4 text-primary-500" />
          </div>
          <div className="hidden sm:block">
            <h1 className="text-base font-bold tracking-tight text-white select-none">
              GenAI<span className="text-primary-500">BI</span>
            </h1>
          </div>
        </Link>

        <div className="hidden md:flex items-center gap-1">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-2 px-4 py-2 rounded-apple text-sm font-medium transition-all duration-200 ${
                isActive(item.path)
                  ? 'bg-primary-500/10 text-primary-400'
                  : 'text-dark-400 hover:text-dark-200 hover:bg-white/[0.04]'
              }`}
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </Link>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <div className="relative hidden md:block" ref={userMenuRef}>
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-2.5 px-2 py-1.5 rounded-apple hover:bg-white/[0.04] transition-colors"
              aria-haspopup="true"
              aria-expanded={userMenuOpen}
            >
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center text-white text-sm font-bold">
                {initial}
              </div>
              <div className="hidden lg:block text-left">
                <p className="text-sm font-medium text-dark-100 leading-tight max-w-[140px] truncate">
                  {displayName}
                </p>
                <p className="text-[11px] text-dark-500 leading-tight capitalize">
                  {user?.role || 'user'}
                </p>
              </div>
              <ChevronDown className={`w-3.5 h-3.5 text-dark-400 transition-transform ${userMenuOpen ? 'rotate-180' : ''}`} />
            </button>

            <AnimatePresence>
              {userMenuOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -6, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -6, scale: 0.98 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 mt-2 w-64 bg-dark-800/95 border border-white/[0.08] rounded-apple-lg shadow-apple backdrop-blur-2xl overflow-hidden"
                >
                  <div className="px-4 py-3 border-b border-white/[0.06]">
                    <p className="text-sm font-medium text-dark-100 truncate">{displayName}</p>
                    <p className="text-xs text-dark-500 truncate mt-0.5">{user?.email}</p>
                  </div>
                  <div className="p-1.5">
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-apple text-sm text-red-400 hover:bg-red-500/10 transition-colors min-h-[44px]"
                    >
                      <LogOut className="w-4 h-4" />
                      Sign Out
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="w-10 h-10 flex items-center justify-center rounded-apple text-dark-400 hover:text-dark-200 hover:bg-white/[0.04] transition-colors md:hidden"
            aria-label="Toggle navigation menu"
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="md:hidden mt-3 pt-3 border-t border-white/[0.05] overflow-hidden"
          >
            <div className="space-y-1 pb-2">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileOpen(false)}
                  className={`min-h-[44px] flex items-center gap-3 px-4 py-3 rounded-apple text-sm font-medium transition-all ${
                    isActive(item.path)
                      ? 'bg-primary-500/10 text-primary-400'
                      : 'text-dark-400 hover:text-dark-200 hover:bg-white/[0.04]'
                  }`}
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </Link>
              ))}
              <div className="mt-2 pt-3 border-t border-white/[0.05]">
                <div className="flex items-center gap-3 px-4 py-2">
                  <UserCircle className="w-5 h-5 text-dark-400" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-dark-100 truncate">{displayName}</p>
                    <p className="text-xs text-dark-500 truncate">{user?.email}</p>
                  </div>
                </div>
                <button
                  onClick={handleLogout}
                  className="min-h-[44px] w-full flex items-center gap-3 px-4 py-3 rounded-apple text-sm font-medium text-red-400 hover:bg-red-500/10 transition-all"
                >
                  <LogOut className="w-4 h-4" />
                  Sign Out
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
};

export default Navbar;
