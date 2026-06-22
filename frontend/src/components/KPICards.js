import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Database, Rows3, Columns3, TrendingUp } from 'lucide-react';

const useCountUp = (end, duration = 1200) => {
  const [count, setCount] = useState(0);
  const ref = useRef(null);

  useEffect(() => {
    if (!end || end === 0) { setCount(0); return; }
    const numEnd = typeof end === 'string' ? parseInt(end.replace(/,/g, ''), 10) : end;
    if (isNaN(numEnd)) { setCount(0); return; }

    let startTime = null;
    const step = (timestamp) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.floor(eased * numEnd));
      if (progress < 1) ref.current = requestAnimationFrame(step);
    };
    ref.current = requestAnimationFrame(step);
    return () => { if (ref.current) cancelAnimationFrame(ref.current); };
  }, [end, duration]);

  return count;
};

const AnimatedNumber = ({ value }) => {
  const num = typeof value === 'string' ? parseInt(value.replace(/,/g, ''), 10) : value;
  const animated = useCountUp(num);
  return <>{animated.toLocaleString()}</>;
};

const KPICards = ({ datasets, queryCount }) => {
  const totalRows = datasets.reduce((sum, d) => sum + (d.row_count || 0), 0);
  const totalCols = datasets.reduce((sum, d) => sum + (d.column_count || 0), 0);

  const cards = [
    {
      label: 'Datasets',
      value: datasets.length,
      icon: Database,
      gradient: 'from-primary-500 to-primary-700',
      glow: 'shadow-primary-500/20',
    },
    {
      label: 'Total Rows',
      value: totalRows,
      icon: Rows3,
      gradient: 'from-red-500 to-rose-700',
      glow: 'shadow-red-500/20',
    },
    {
      label: 'Total Columns',
      value: totalCols,
      icon: Columns3,
      gradient: 'from-amber-500 to-amber-700',
      glow: 'shadow-amber-500/20',
    },
    {
      label: 'Queries Run',
      value: queryCount || 0,
      icon: TrendingUp,
      gradient: 'from-emerald-500 to-emerald-700',
      glow: 'shadow-emerald-500/20',
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card, i) => (
        <motion.div
          key={card.label}
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ delay: i * 0.08, type: 'spring', stiffness: 200 }}
          className={`glass-card-hover p-5 shadow-lg ${card.glow} hover:scale-[1.02] transition-transform`}
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-dark-400 text-sm font-medium">{card.label}</span>
            <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${card.gradient} flex items-center justify-center shadow-lg`}>
              <card.icon className="w-5 h-5 text-white" />
            </div>
          </div>
          <p className="text-2xl sm:text-3xl font-bold text-dark-100">
            <AnimatedNumber value={card.value} />
          </p>
        </motion.div>
      ))}
    </div>
  );
};

export default KPICards;
