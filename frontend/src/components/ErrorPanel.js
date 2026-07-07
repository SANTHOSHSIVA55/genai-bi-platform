import React from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, RefreshCw, Terminal, FileWarning } from 'lucide-react';

const ErrorPanel = ({ question, generatedSql, issues, onRegenerate }) => {
  if (!issues || issues.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="error-panel"
    >
      <div className="error-panel-title">
        <FileWarning className="w-4 h-4" />
        AI Query Analysis
      </div>

      <div className="space-y-3">
        <div>
          <div className="error-panel-label">User Intent</div>
          <div className="text-sm text-dark-200 bg-dark-950/50 rounded-apple p-3 border border-white/[0.04]">
            {question}
          </div>
        </div>

        <div>
          <div className="error-panel-label">Generated SQL</div>
          <div className="error-panel-code">
            {generatedSql || 'N/A'}
          </div>
        </div>

        <div>
          <div className="error-panel-label flex items-center gap-1.5">
            <AlertTriangle className="w-3 h-3 text-red-400" />
            Issue Detected
          </div>
          <div className="bg-red-500/8 rounded-apple p-3 border border-red-500/15">
            <ul className="space-y-1">
              {issues.map((issue, i) => (
                <li key={i} className="text-xs text-red-300 flex items-start gap-2">
                  <span className="text-red-400 mt-0.5">&bull;</span>
                  {issue}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {onRegenerate && (
          <button
            onClick={onRegenerate}
            className="w-full mt-2 flex items-center justify-center gap-2 px-4 py-2.5
                       bg-primary-500/10 border border-primary-500/20 text-primary-300
                       hover:bg-primary-500/20 hover:border-primary-500/40
                       rounded-apple transition-all text-sm font-medium"
          >
            <RefreshCw className="w-4 h-4" />
            Regenerate Query
          </button>
        )}
      </div>
    </motion.div>
  );
};

export default ErrorPanel;
