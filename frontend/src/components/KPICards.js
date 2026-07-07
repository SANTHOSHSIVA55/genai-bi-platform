import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Database, Rows3, Columns3, TrendingUp } from 'lucide-react';

const useCountUp = (end, duration = 1000) => {
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
      accent: 'from-primary-500/10 to-primary-600/5',
      iconBg: 'bg-primary-500/10',
      iconColor: 'text-primary-400',
    },
    {
      label: 'Total Rows',
      value: totalRows,
      icon: Rows3,
      accent: 'from-red-500/10 to-rose-600/5',
      iconBg: 'bg-red-500/10',
      iconColor: 'text-red-400',
    },
    {
      label: 'Total Columns',
      value: totalCols,
      icon: Columns3,
      accent: 'from-apple-orange/10 to-amber-600/5',
      iconBg: 'bg-apple-orange/10',
      iconColor: 'text-apple-orange',
    },
    {
      label: 'Queries Run',
      value: queryCount || 0,
      icon: TrendingUp,
      accent: 'from-apple-green/10 to-emerald-600/5',
      iconBg: 'bg-apple-green/10',
      iconColor: 'text-apple-green',
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {cards.map((card, i) => (
        <motion.div
          key={card.label}
          initial={{ opacity: 0, y: 12, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ delay: i * 0.06, type: 'spring', stiffness: 200, damping: 20 }}
          className="kpi-card"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="kpi-label">{card.label}</span>
            <div className={`w-8 h-8 rounded-apple ${card.iconBg} border border-white/[0.05] flex items-center justify-center`}>
              <card.icon className={`w-4 h-4 ${card.iconColor}`} />
            </div>
          </div>
          <p className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            <AnimatedNumber value={card.value} />
          </p>
        </motion.div>
      ))}
    </div>
  );
};

export default KPICards;
