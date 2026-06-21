import React from 'react';
import { motion } from 'framer-motion';
import {
  Lightbulb, AlertTriangle, MessageSquare, FileText, ChevronRight,
} from 'lucide-react';

const SummaryPanel = ({ summary, generatedSql, onFollowUp }) => {
  if (!summary) return null;

  const {
    executive_summary = [],
    recommendations = [],
    risks = [],
    follow_up_questions = [],
  } = summary;

  const sections = [
    {
      title: 'Executive Summary',
      icon: FileText,
      items: executive_summary,
      color: 'primary',
      bg: 'from-primary-500/10 to-primary-600/5',
      iconColor: 'text-primary-400',
    },
    {
      title: 'Recommendations',
      icon: Lightbulb,
      items: recommendations,
      color: 'emerald',
      bg: 'from-emerald-500/10 to-emerald-600/5',
      iconColor: 'text-emerald-400',
    },
    {
      title: 'Risks & Concerns',
      icon: AlertTriangle,
      items: risks,
      color: 'amber',
      bg: 'from-amber-500/10 to-amber-600/5',
      iconColor: 'text-amber-400',
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="space-y-4"
    >
      {/* Generated SQL */}
      {generatedSql && (
        <div className="glass-card p-5">
          <h4 className="text-sm font-medium text-dark-400 mb-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            Generated SQL
          </h4>
          <pre className="text-sm text-dark-300 bg-dark-900 p-4 rounded-xl overflow-x-auto font-mono">
            {generatedSql}
          </pre>
        </div>
      )}

      {/* Insight Sections */}
      {sections.map((section) => (
        <div key={section.title} className="glass-card p-5">
          <h4 className={`text-sm font-semibold mb-3 flex items-center gap-2 ${section.iconColor}`}>
            <section.icon className="w-4 h-4" />
            {section.title}
          </h4>
          <div className="space-y-2">
            {section.items.map((item, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 * i }}
                className={`flex items-start gap-3 p-3 rounded-xl bg-gradient-to-r ${section.bg}`}
              >
                <ChevronRight className={`w-4 h-4 mt-0.5 flex-shrink-0 ${section.iconColor}`} />
                <p className="text-sm text-dark-200">{item}</p>
              </motion.div>
            ))}
          </div>
        </div>
      ))}

      {/* Follow-up Questions */}
      {follow_up_questions.length > 0 && (
        <div className="glass-card p-5">
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2 text-primary-500">
            <MessageSquare className="w-4 h-4" />
            Suggested Follow-ups
          </h4>
          <div className="flex flex-wrap gap-2">
            {follow_up_questions.map((q, i) => (
              <button
                key={i}
                onClick={() => onFollowUp && onFollowUp(q)}
                className="px-4 py-2 text-sm rounded-md bg-primary-500/10 border border-primary-500/20 text-primary-300
                           hover:bg-primary-500/20 hover:border-primary-500/40 transition-all cursor-pointer"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default SummaryPanel;
