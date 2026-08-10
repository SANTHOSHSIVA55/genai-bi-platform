import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Workflow, Check, SkipForward, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';

const STATUS_META = {
  done: { icon: Check, className: 'bg-apple-green/10 text-apple-green border-apple-green/20' },
  skipped: { icon: SkipForward, className: 'bg-dark-700/40 text-dark-500 border-white/[0.06]' },
  in_progress: { icon: Loader2, className: 'bg-primary-500/10 text-primary-400 border-primary-500/25' },
};

const PipelineStages = ({ stages }) => {
  const [expanded, setExpanded] = useState(false);

  if (!stages || stages.length === 0) return null;

  const doneCount = stages.filter((s) => s.status === 'done').length;
  const skippedCount = stages.filter((s) => s.status === 'skipped').length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.05 }}
      className="glass-card overflow-hidden"
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <Workflow className="w-4 h-4 text-primary-400" />
          <span className="text-sm font-medium text-dark-200">Processing Pipeline</span>
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-dark-700/50 text-dark-400">
            {doneCount}/{stages.length} completed
            {skippedCount > 0 ? ` · ${skippedCount} skipped` : ''}
          </span>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-dark-400" /> : <ChevronDown className="w-4 h-4 text-dark-400" />}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-white/[0.04]"
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 p-4">
              {stages.map((s, i) => {
                const meta = STATUS_META[s.status] || STATUS_META.skipped;
                const Icon = meta.icon;
                return (
                  <div
                    key={i}
                    className={`flex items-start gap-2.5 px-3 py-2.5 rounded-apple border ${meta.className}`}
                    title={s.detail || s.stage}
                  >
                    <Icon className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${s.status === 'in_progress' ? 'animate-spin' : ''}`} />
                    <div className="min-w-0">
                      <p className="text-xs font-medium">{s.stage}</p>
                      {s.detail && <p className="text-[11px] opacity-70 truncate">{s.detail}</p>}
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default PipelineStages;
