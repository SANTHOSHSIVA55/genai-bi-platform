import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';

const ConfirmDialog = ({ open, title, message, confirmLabel, cancelLabel, onConfirm, onCancel, loading }) => {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80 backdrop-blur-sm"
          onClick={onCancel}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 12 }}
            transition={{ duration: 0.18 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-sm glass-card p-6"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
          >
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-apple bg-red-500/10 border border-red-500/20 flex items-center justify-center flex-shrink-0">
                <AlertTriangle className="w-5 h-5 text-red-400" />
              </div>
              <div className="min-w-0">
                <h3 id="confirm-title" className="text-base font-semibold text-white mb-1">
                  {title}
                </h3>
                {message && <p className="text-dark-400 text-sm">{message}</p>}
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={onCancel} disabled={loading} className="btn-secondary flex-1 text-sm">
                {cancelLabel || 'Cancel'}
              </button>
              <button
                onClick={onConfirm}
                disabled={loading}
                className="btn-primary flex-1 text-sm !bg-red-600 !hover:bg-red-500 flex items-center justify-center gap-2"
              >
                {confirmLabel || 'Delete'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default ConfirmDialog;
