import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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

  const hasContent = executive_summary.length || recommendations.length || risks.length;

  const sections = [
    {
      title: 'Executive Summary',
      icon: FileText,
      items: executive_summary,
      iconColor: 'text-primary-400',
      borderColor: 'border-primary-500/10',
      bgAccent: 'from-primary-500/5',
    },
    {
      title: 'Recommendations',
      icon: Lightbulb,
      items: recommendations,
      iconColor: 'text-apple-green',
      borderColor: 'border-apple-green/10',
      bgAccent: 'from-apple-green/5',
    },
    {
      title: 'Risks & Concerns',
      icon: AlertTriangle,
      items: risks,
      iconColor: 'text-apple-orange',
      borderColor: 'border-apple-orange/10',
      bgAccent: 'from-apple-orange/5',
    },
  ].filter(s => s.items.length > 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="space-y-4"
    >
      {generatedSql && (
        <div className="glass-card p-5">
          <h4 className="text-sm font-medium text-dark-400 mb-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-apple-green" />
            Generated SQL
          </h4>
          <pre className="text-sm text-dark-300 bg-dark-950/50 p-4 rounded-apple overflow-x-auto font-mono leading-relaxed border border-white/[0.04]">
            {generatedSql}
          </pre>
        </div>
      )}

      <AnimatePresence>
        {sections.map((section) => (
          <motion.div
            key={section.title}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card p-5"
          >
            <h4 className={`text-sm font-semibold mb-3 flex items-center gap-2 ${section.iconColor}`}>
              <section.icon className="w-4 h-4" />
              {section.title}
            </h4>
            <div className="space-y-2">
              {section.items.map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.04 * i }}
                  className={`flex items-start gap-3 p-3 rounded-apple bg-gradient-to-r ${section.bgAccent} to-transparent border border-white/[0.03]`}
                >
                  <ChevronRight className={`w-4 h-4 mt-0.5 flex-shrink-0 ${section.iconColor}`} />
                  <p className="text-sm text-dark-200 leading-relaxed">{item}</p>
                </motion.div>
              ))}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>

      {follow_up_questions.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-5"
        >
          <h4 className="text-sm font-semibold mb-3 flex items-center gap-2 text-primary-400">
            <MessageSquare className="w-4 h-4" />
            Suggested Follow-ups
          </h4>
          <div className="flex flex-wrap gap-2">
            {follow_up_questions.map((q, i) => (
              <motion.button
                key={i}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.04 * i }}
                onClick={() => onFollowUp && onFollowUp(q)}
                className="px-4 py-2.5 text-sm rounded-apple bg-primary-500/8 border border-primary-500/15 text-primary-300
                           hover:bg-primary-500/15 hover:border-primary-500/30 transition-all cursor-pointer text-left"
              >
                {q}
              </motion.button>
            ))}
          </div>
        </motion.div>
      )}

      {!hasContent && follow_up_questions.length === 0 && !generatedSql && (
        <div className="glass-card p-8 text-center">
          <p className="text-dark-500 text-sm">No insights generated for this query.</p>
        </div>
      )}
    </motion.div>
  );
};

export default SummaryPanel;
