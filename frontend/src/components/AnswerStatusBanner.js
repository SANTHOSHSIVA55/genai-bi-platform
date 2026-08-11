import React from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, HelpCircle, XCircle, Database } from 'lucide-react';

const STYLES = {
  insufficient: {
    icon: HelpCircle,
    title: 'Not enough data to answer this',
    tone: 'amber',
  },
  clarification: {
    icon: AlertCircle,
    title: 'Let me clarify that',
    tone: 'amber',
  },
  failed: {
    icon: XCircle,
    title: 'I could not produce a trustworthy answer',
    tone: 'red',
  },
};

const AnswerStatusBanner = ({ answerStatus, sufficiency = {}, summary = {}, datasetsUsed = [] }) => {
  if (!answerStatus || answerStatus === 'answered') return null;

  const config = STYLES[answerStatus] || STYLES.failed;
  const Icon = config.icon;
  const tone = config.tone;

  const missing = Array.isArray(sufficiency?.missing) ? sufficiency.missing : [];
  const available = Array.isArray(sufficiency?.available) ? sufficiency.available : [];
  const summaryLines = Array.isArray(summary?.executive_summary) ? summary.executive_summary : [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`glass-card p-5 border ${
        tone === 'red'
          ? 'border-red-500/15'
          : 'border-amber-500/15'
      }`}
      role="status"
    >
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 w-8 h-8 rounded-apple-lg flex items-center justify-center flex-shrink-0 ${
          tone === 'red' ? 'bg-red-500/10 text-red-400' : 'bg-amber-500/10 text-amber-300'
        }`}>
          <Icon className="w-5 h-5" />
        </span>
        <div className="min-w-0 space-y-2">
          <p className={`font-semibold text-sm ${
            tone === 'red' ? 'text-red-300' : 'text-amber-300'
          }`}>
            {config.title}
          </p>

          {missing.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-dark-500">This dataset is missing the data needed to answer the question:</p>
              <ul className="space-y-1">
                {missing.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-dark-200">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {available.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-dark-500">What was found:</p>
              <ul className="space-y-1">
                {available.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-dark-400">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400/70 flex-shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {summaryLines.map((line, i) => (
            <p key={i} className="text-sm text-dark-200 leading-relaxed">{line}</p>
          ))}

          {datasetsUsed.length > 0 && (
            <p className="flex items-center gap-1.5 text-[11px] text-dark-500 pt-1">
              <Database className="w-3 h-3" />
              Checked across: {datasetsUsed.join(', ')}
            </p>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default AnswerStatusBanner;
