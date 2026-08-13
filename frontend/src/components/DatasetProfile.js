import React from 'react';
import { motion } from 'framer-motion';
import {
  LayoutGrid, Rows, AlertTriangle, Sparkles, Hash, Tag, CalendarClock,
  Type, ToggleLeft, KeyRound, Loader2,
} from 'lucide-react';

const TYPE_ICONS = {
  numeric: Hash,
  categorical: Tag,
  date: CalendarClock,
  text: Type,
  boolean: ToggleLeft,
  id: KeyRound,
};

const TYPE_LABELS = {
  numeric: 'Numeric',
  categorical: 'Categorical',
  date: 'Date',
  text: 'Text',
  boolean: 'Boolean',
  id: 'ID',
};

import SkeletonLoader from './SkeletonLoader';

const DatasetProfile = ({ profile, datasetName, loading }) => {
  if (loading) {
    return <SkeletonLoader.ProfileSkeleton />;
  }

  if (!profile || !profile.overview) return null;

  const { overview, insights, currency } = profile;
  const typeGroups = [
    { key: 'numeric_columns', label: 'Numeric' },
    { key: 'categorical_columns', label: 'Categorical' },
    { key: 'date_columns', label: 'Date' },
    { key: 'text_columns', label: 'Text' },
    { key: 'boolean_columns', label: 'Boolean' },
    { key: 'id_columns', label: 'ID' },
  ].filter((g) => (overview[g.key] || []).length > 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="glass-card p-5"
    >
      <h3 className="text-sm font-semibold text-dark-200 mb-4 flex items-center gap-2">
        <LayoutGrid className="w-4 h-4 text-primary-400" />
        <span className="truncate">{datasetName || 'Dataset'} Overview</span>
        {currency && <span className="text-[11px] px-2 py-0.5 rounded-full bg-primary-500/10 text-primary-300">Currency: {currency}</span>}
      </h3>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3 rounded-apple bg-dark-800/40 border border-white/[0.04]">
          <div className="flex items-center gap-1.5 text-dark-500 text-[11px] uppercase tracking-wider mb-1">
            <Rows className="w-3 h-3" /> Rows
          </div>
          <p className="text-lg font-bold text-white">{(overview.row_count || 0).toLocaleString()}</p>
        </div>
        <div className="p-3 rounded-apple bg-dark-800/40 border border-white/[0.04]">
          <div className="flex items-center gap-1.5 text-dark-500 text-[11px] uppercase tracking-wider mb-1">
            <LayoutGrid className="w-3 h-3" /> Columns
          </div>
          <p className="text-lg font-bold text-white">{overview.column_count || 0}</p>
        </div>
      </div>

      <div className="space-y-2 mb-4">
        {typeGroups.map((g) => {
          const Icon = TYPE_ICONS[g.key.replace('_columns', '')] || Hash;
          const cols = overview[g.key];
          return (
            <div key={g.key} className="flex items-start gap-2 text-sm">
              <Icon className="w-3.5 h-3.5 mt-0.5 text-dark-500 flex-shrink-0" />
              <div className="min-w-0">
                <span className="text-dark-400 text-xs">{TYPE_LABELS[g.key.replace('_columns', '')]}:</span>{' '}
                <span className="text-dark-200 text-xs break-words">{cols.join(', ')}</span>
              </div>
            </div>
          );
        })}
        {overview.total_missing > 0 && (
          <div className="flex items-start gap-2 text-sm text-amber-400">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span className="text-xs">{overview.total_missing} missing value{overview.total_missing !== 1 ? 's' : ''}</span>
          </div>
        )}
      </div>

      {insights && insights.length > 0 && (
        <>
          <h4 className="text-xs font-semibold text-dark-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-primary-400" />
            Auto Insights
          </h4>
          <div className="space-y-2">
            {insights.slice(0, 4).map((ins, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.05 * i }}
                className="p-3 rounded-apple bg-gradient-to-r from-primary-500/5 to-transparent border border-white/[0.03]"
              >
                <p className="text-xs font-medium text-primary-300 mb-0.5">{ins.title}</p>
                <p className="text-xs text-dark-300 leading-relaxed">{ins.text}</p>
              </motion.div>
            ))}
          </div>
        </>
      )}
    </motion.div>
  );
};

export default DatasetProfile;
