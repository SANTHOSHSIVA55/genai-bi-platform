import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Loader2, Database, AlertCircle } from 'lucide-react';
import { getDatasetPreview } from '../api/api';

const DatasetPreviewModal = ({ datasetId, datasetName, open, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (!open || !datasetId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPreview(null);
    getDatasetPreview(datasetId)
      .then((res) => {
        if (!cancelled) setPreview(res.data);
      })
      .catch((err) => {
        if (!cancelled) {
          const detail = err.response?.data?.detail;
          setError(typeof detail === 'string' ? detail : 'Could not load dataset preview.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, datasetId]);

  const columns = preview?.columns || [];
  const rows = preview?.sample_rows || [];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ duration: 0.18 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-3xl max-h-[80vh] glass-card p-5 flex flex-col"
            role="dialog"
            aria-modal="true"
            aria-labelledby="preview-title"
          >
            <div className="flex items-center justify-between mb-4">
              <h3 id="preview-title" className="text-base font-semibold text-white flex items-center gap-2">
                <Database className="w-4 h-4 text-primary-400" />
                {datasetName || 'Dataset Preview'}
              </h3>
              <button
                onClick={onClose}
                aria-label="Close preview"
                className="min-h-[36px] min-w-[36px] flex items-center justify-center p-2 rounded-apple text-dark-400 hover:text-dark-100 hover:bg-white/[0.04] transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="overflow-auto flex-1">
              {loading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 className="w-8 h-8 text-primary-400 animate-spin" />
                </div>
              ) : error ? (
                <div className="flex flex-col items-center gap-3 py-12 text-center">
                  <AlertCircle className="w-7 h-7 text-red-400" />
                  <p className="text-dark-300 text-sm">{error}</p>
                </div>
              ) : rows.length === 0 ? (
                <p className="text-dark-500 text-sm text-center py-12">No preview data available.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/[0.06]">
                        {columns.map((col) => (
                          <th
                            key={col}
                            className="px-3 py-2 text-left text-dark-400 font-medium uppercase text-[11px] tracking-wider whitespace-nowrap"
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, i) => (
                        <tr key={i} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                          {columns.map((col) => (
                            <td key={col} className="px-3 py-2 text-dark-200 whitespace-nowrap">
                              {row[col] != null ? String(row[col]) : '\u2014'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="text-dark-500 text-xs text-center py-3">
                    Showing {rows.length} sample rows
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default DatasetPreviewModal;
