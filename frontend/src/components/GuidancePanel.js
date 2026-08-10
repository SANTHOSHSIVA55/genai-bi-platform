import React from 'react';
import { motion } from 'framer-motion';
import { Info, MessageSquare, ChevronDown, ChevronUp, Code } from 'lucide-react';
import { useState } from 'react';

const GuidancePanel = ({ message, issues, generatedSql, followUps, onFollowUp }) => {
  const [showTechnical, setShowTechnical] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-6 border-amber-500/20"
    >
      <div className="flex items-start gap-3.5">
        <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center flex-shrink-0">
          <Info className="w-5 h-5 text-amber-400" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-semibold text-dark-100 mb-1.5">Let me clarify that for you</h4>
          <p className="text-sm text-dark-300 leading-relaxed">{message}</p>
        </div>
      </div>

      {followUps && followUps.length > 0 && (
        <div className="mt-5">
          <p className="text-[11px] uppercase tracking-wider text-dark-500 mb-2 flex items-center gap-1.5">
            <MessageSquare className="w-3 h-3" />
            You could ask
          </p>
          <div className="flex flex-wrap gap-2">
            {followUps.map((q, i) => (
              <button
                key={i}
                onClick={() => onFollowUp && onFollowUp(q)}
                className="px-4 py-2 text-sm rounded-apple bg-amber-500/8 border border-amber-500/15 text-amber-300
                           hover:bg-amber-500/15 hover:border-amber-500/30 transition-all cursor-pointer text-left"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {issues && issues.length > 0 && (
        <div className="mt-4 border-t border-white/[0.05] pt-3">
          <button
            onClick={() => setShowTechnical(!showTechnical)}
            className="flex items-center gap-2 text-xs text-dark-400 hover:text-dark-200 transition-colors"
          >
            <Code className="w-3.5 h-3.5" />
            Technical details
            {showTechnical ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showTechnical && (
            <div className="mt-2 space-y-2">
              {issues.map((issue, i) => (
                <div key={i} className="text-xs text-dark-400 bg-dark-950/50 rounded-apple p-3 border border-white/[0.04]">
                  {issue}
                </div>
              ))}
              {generatedSql && (
                <pre className="text-xs text-dark-400 bg-dark-950/50 rounded-apple p-3 border border-white/[0.04] overflow-x-auto font-mono">
                  {generatedSql}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
};

export default GuidancePanel;
