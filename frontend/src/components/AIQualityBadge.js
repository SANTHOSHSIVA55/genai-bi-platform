import React from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, XCircle, AlertCircle, Target } from 'lucide-react';

const ANALYSIS_STEPS = [
  { label: 'Intent Detected', key: 'intent_detected' },
  { label: 'SQL Generated', key: 'sql_generated' },
  { label: 'SQL Validated', key: 'sql_validated' },
  { label: 'Chart Selected', key: 'chart_selected_correctly' },
  { label: 'Summary Generated', key: 'summary_generated' },
  { label: 'Recommendations', key: 'recommendations_generated' },
  { label: 'Follow-up Questions', key: 'follow_up_generated' },
  { label: 'SQL Executed', key: 'sql_executed_successfully' },
];

const ScoreRing = ({ score, size = 72 }) => {
  const radius = size * 0.4;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const strokeWidth = 5;

  const color = score >= 80 ? '#34c759' : score >= 60 ? '#ff9500' : '#ff3b30';

  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        stroke="rgba(255,255,255,0.06)"
        strokeWidth={strokeWidth}
        fill="none"
      />
      <motion.circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        stroke={color}
        strokeWidth={strokeWidth}
        fill="none"
        strokeLinecap="round"
        strokeDasharray={circumference}
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: offset }}
        transition={{ duration: 1, ease: 'easeOut' }}
      />
      <text
        x="50%"
        y="50%"
        textAnchor="middle"
        dy="0.35em"
        fill="#e8e8ed"
        fontSize={size * 0.2}
        fontWeight="bold"
        fontFamily="Inter, sans-serif"
        transform="rotate(90, 36, 36)"
      >
        {score}%
      </text>
    </svg>
  );
};

const AIQualityBadge = ({ quality }) => {
  if (!quality) return null;

  const score = quality.overall_score ?? (
    ANALYSIS_STEPS.filter(s => quality[s.key]).length / ANALYSIS_STEPS.length * 100
  );

  const hasIssues = quality.issues && quality.issues.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-5"
    >
      <div className="flex items-start gap-5 mb-4">
        <div className="flex-shrink-0">
          <ScoreRing score={Math.round(score)} />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-semibold text-dark-200 mb-1 flex items-center gap-2">
            <Target className="w-4 h-4 text-primary-400" />
            AI Analysis Quality
          </h4>
          <p className="text-xs text-dark-400">
            {score >= 80 ? 'High confidence' : score >= 60 ? 'Moderate confidence' : 'Low confidence'} in AI-generated results
          </p>
          {hasIssues && (
            <div className="mt-2 flex items-start gap-1.5 text-xs text-red-400">
              <AlertCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{quality.issues[0]}</span>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {ANALYSIS_STEPS.map((step) => {
          const pass = quality[step.key];
          return (
            <motion.div
              key={step.key}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-apple text-xs font-medium border ${
                pass
                  ? 'bg-apple-green/8 text-apple-green border-apple-green/12'
                  : 'bg-red-500/8 text-red-400 border-red-500/12'
              }`}
            >
              {pass ? (
                <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
              ) : (
                <XCircle className="w-3.5 h-3.5 flex-shrink-0" />
              )}
              <span className="truncate">{step.label}</span>
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
};

export default AIQualityBadge;
