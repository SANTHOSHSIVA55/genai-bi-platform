import React from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, XCircle, AlertCircle } from 'lucide-react';

const AIQualityBadge = ({ quality }) => {
  if (!quality) return null;

  const items = [
    { label: 'Intent Detected', key: 'intent_detected' },
    { label: 'SQL Validated', key: 'sql_validated' },
    { label: 'Chart Selected Correctly', key: 'chart_selected_correctly' },
    { label: 'Summary Generated', key: 'summary_generated' },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-4"
    >
      <h4 className="text-xs font-semibold text-dark-400 uppercase tracking-wider mb-3">
        AI Analysis Quality
      </h4>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => {
          const pass = quality[item.key];
          return (
            <div
              key={item.key}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-[11px] font-medium border ${
                pass
                  ? 'bg-apple-green/8 text-apple-green border-apple-green/12'
                  : 'bg-red-500/8 text-red-400 border-red-500/12'
              }`}
            >
              {pass ? (
                <CheckCircle2 className="w-3 h-3" />
              ) : (
                <XCircle className="w-3 h-3" />
              )}
              {item.label}
            </div>
          );
        })}
      </div>
      {quality.issues && quality.issues.length > 0 && (
        <div className="mt-2 text-xs text-red-400 flex items-center gap-1.5">
          <AlertCircle className="w-3 h-3" />
          {quality.issues[0]}
        </div>
      )}
    </motion.div>
  );
};

export default AIQualityBadge;
