import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';

const AuthLayout = ({ title, subtitle, children, footer }) => (
  <div className="min-h-screen bg-dark-950 grid-bg relative flex flex-col items-center justify-center px-4 py-12">
    <div className="absolute inset-0 bg-gradient-to-b from-dark-950/60 via-transparent to-dark-950 pointer-events-none" />

    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="relative z-10 w-full max-w-md"
    >
      <div className="mb-8 text-center">
        <Link to="/" className="inline-flex items-center gap-2.5 group">
          <div className="w-10 h-10 rounded-apple bg-dark-800 border border-primary-500/20 flex items-center justify-center group-hover:border-primary-500/50 transition-all duration-300">
            <Sparkles className="w-5 h-5 text-primary-500" />
          </div>
          <span className="text-xl font-black tracking-tight text-white select-none">
            GenAI<span className="text-primary-500">BI</span>
          </span>
        </Link>
        <h1 className="text-2xl font-bold text-white mt-6 mb-1.5">{title}</h1>
        {subtitle && <p className="text-dark-400 text-sm">{subtitle}</p>}
      </div>

      <div className="glass-card p-6 sm:p-8">{children}</div>

      {footer && <p className="text-dark-500 text-sm text-center mt-6">{footer}</p>}
    </motion.div>
  </div>
);

export default AuthLayout;
