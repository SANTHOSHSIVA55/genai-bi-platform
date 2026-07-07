import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, Upload, History, Sparkles,
  Menu, X
} from 'lucide-react';

const Navbar = () => {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/upload', label: 'Upload', icon: Upload },
    { path: '/history', label: 'History', icon: History },
  ];

  const isActive = (path) => location.pathname === path;

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

        <div className="flex items-center gap-3 md:hidden">
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="w-10 h-10 flex items-center justify-center rounded-apple text-dark-400 hover:text-dark-200 hover:bg-white/[0.04] transition-colors"
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
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
};

export default Navbar;
