import React from 'react';
import { motion } from 'framer-motion';
import { Database, Rows3, Columns3, TrendingUp } from 'lucide-react';

const KPICards = ({ datasets, queryCount }) => {
  const totalRows = datasets.reduce((sum, d) => sum + (d.row_count || 0), 0);
  const totalCols = datasets.reduce((sum, d) => sum + (d.column_count || 0), 0);

  const cards = [
    {
      label: 'Datasets',
      value: datasets.length,
      icon: Database,
      color: 'from-primary-500 to-primary-700',
      shadow: 'shadow-primary-500/10',
    },
    {
      label: 'Total Rows',
      value: totalRows.toLocaleString(),
      icon: Rows3,
      color: 'from-red-500 to-rose-700',
      shadow: 'shadow-red-500/10',
    },
    {
      label: 'Total Columns',
      value: totalCols.toLocaleString(),
      icon: Columns3,
      color: 'from-amber-500 to-amber-700',
      shadow: 'shadow-amber-500/10',
    },
    {
      label: 'Queries Run',
      value: queryCount || 0,
      icon: TrendingUp,
      color: 'from-dark-600 to-dark-700 border border-dark-600/30',
      shadow: 'shadow-dark-900/10',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, i) => (
        <motion.div
          key={card.label}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.1 }}
          className={`glass-card-hover p-5 ${card.shadow}`}
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-dark-400 text-sm font-medium">{card.label}</span>
            <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${card.color} flex items-center justify-center`}>
              <card.icon className="w-5 h-5 text-white" />
            </div>
          </div>
          <p className="text-3xl font-bold text-dark-100">{card.value}</p>
        </motion.div>
      ))}
    </div>
  );
};

export default KPICards;
