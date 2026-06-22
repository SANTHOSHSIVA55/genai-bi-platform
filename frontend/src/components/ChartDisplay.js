import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { BarChart3, TrendingUp, PieChart as PieIcon, AreaChart as AreaIcon, Table2 } from 'lucide-react';

const COLORS = [
  '#e50914', '#ff3e4b', '#ffa00a', '#b81d24', '#ff7e8a',
  '#ffc9c9', '#8c141a', '#e5b809', '#f43f5e', '#6366f1',
];

const formatNumber = (val) => {
  if (val == null || val === '') return '—';
  if (typeof val === 'string' && isNaN(Number(val))) return val;
  const num = Number(val);
  if (isNaN(num)) return String(val);
  if (Math.abs(num) >= 1e9) return (num / 1e9).toFixed(1) + 'B';
  if (Math.abs(num) >= 1e6) return (num / 1e6).toFixed(1) + 'M';
  if (Math.abs(num) >= 1e3) return (num / 1e3).toFixed(1) + 'K';
  return num % 1 === 0 ? num.toLocaleString() : num.toFixed(2);
};

const smartAxisKey = (data, columns, preferred) => {
  if (preferred && columns.includes(preferred)) return preferred;
  if (preferred) {
    const match = columns.find(c => c.toLowerCase() === preferred.toLowerCase());
    if (match) return match;
  }
  return columns[0] || '';
};

const ChartDisplay = ({ data, chartConfig }) => {
  const safeData = useMemo(() => {
    if (!data || !Array.isArray(data) || data.length === 0) return [];
    return data.filter(row => row && typeof row === 'object');
  }, [data]);

  if (safeData.length === 0 || !chartConfig) return null;

  const chartType = chartConfig.chart_type || 'table';
  const columns = safeData.length > 0 ? Object.keys(safeData[0]) : [];
  const xKey = smartAxisKey(safeData, columns, chartConfig.x_axis);
  const yKey = smartAxisKey(safeData, columns, chartConfig.y_axis);
  const title = chartConfig.title || 'Query Results';

  const numericCols = columns.filter(c => typeof safeData[0]?.[c] === 'number');
  const hasMultiY = numericCols.length > 1 && chartType !== 'pie';

  const getChartIcon = () => {
    switch (chartType) {
      case 'bar': return <BarChart3 className="w-5 h-5 text-primary-500" />;
      case 'line': return <TrendingUp className="w-5 h-5 text-amber-500" />;
      case 'area': return <AreaIcon className="w-5 h-5 text-emerald-500" />;
      case 'pie': return <PieIcon className="w-5 h-5 text-rose-500" />;
      default: return <Table2 className="w-5 h-5 text-dark-400" />;
    }
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-3 shadow-xl max-w-xs">
        <p className="text-dark-300 text-sm font-medium mb-1.5 truncate">{label}</p>
        {payload.map((entry, i) => (
          <p key={i} className="text-sm flex justify-between gap-4" style={{ color: entry.color }}>
            <span className="truncate">{entry.name}:</span>
            <span className="font-semibold whitespace-nowrap">{formatNumber(entry.value)}</span>
          </p>
        ))}
      </div>
    );
  };

  const tickStyle = { fill: '#808080', fontSize: 11 };
  const gridStyle = { strokeDasharray: '3 3', stroke: '#2f2f2f' };

  const renderBarChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <BarChart data={safeData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
        <CartesianGrid {...gridStyle} />
        <XAxis dataKey={xKey} tick={tickStyle} angle={safeData.length > 8 ? -35 : 0} textAnchor="end" interval={0} />
        <YAxis tick={tickStyle} tickFormatter={formatNumber} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ color: '#94a3b8', paddingTop: 12 }} />
        {hasMultiY ? (
          numericCols.map((col, i) => (
            <Bar key={col} dataKey={col} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />
          ))
        ) : (
          <Bar dataKey={yKey} fill="url(#barGrad)" radius={[4, 4, 0, 0]} />
        )}
        <defs>
          <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e50914" />
            <stop offset="100%" stopColor="#8c141a" />
          </linearGradient>
        </defs>
      </BarChart>
    </ResponsiveContainer>
  );

  const renderLineChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={safeData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
        <CartesianGrid {...gridStyle} />
        <XAxis dataKey={xKey} tick={tickStyle} angle={safeData.length > 8 ? -35 : 0} textAnchor="end" interval={0} />
        <YAxis tick={tickStyle} tickFormatter={formatNumber} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ color: '#94a3b8', paddingTop: 12 }} />
        {hasMultiY ? (
          numericCols.map((col, i) => (
            <Line key={col} type="monotone" dataKey={col} stroke={COLORS[i % COLORS.length]} strokeWidth={2.5}
              dot={{ fill: COLORS[i % COLORS.length], r: 4, strokeWidth: 2, stroke: '#141414' }}
              activeDot={{ r: 7, strokeWidth: 2 }} />
          ))
        ) : (
          <Line type="monotone" dataKey={yKey} stroke="#e50914" strokeWidth={3}
            dot={{ fill: '#e50914', r: 5, strokeWidth: 2, stroke: '#141414' }}
            activeDot={{ r: 8, fill: '#ff3e4b', stroke: '#141414', strokeWidth: 2 }} />
        )}
      </LineChart>
    </ResponsiveContainer>
  );

  const renderAreaChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <AreaChart data={safeData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
        <CartesianGrid {...gridStyle} />
        <XAxis dataKey={xKey} tick={tickStyle} angle={safeData.length > 8 ? -35 : 0} textAnchor="end" interval={0} />
        <YAxis tick={tickStyle} tickFormatter={formatNumber} />
        <Tooltip content={<CustomTooltip />} />
        <Legend wrapperStyle={{ color: '#94a3b8', paddingTop: 12 }} />
        {hasMultiY ? (
          numericCols.map((col, i) => (
            <Area key={col} type="monotone" dataKey={col} stroke={COLORS[i % COLORS.length]} fill={COLORS[i % COLORS.length]}
              fillOpacity={0.15} strokeWidth={2.5} />
          ))
        ) : (
          <Area type="monotone" dataKey={yKey} stroke="#e50914" fill="url(#areaGrad)" strokeWidth={3} />
        )}
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e50914" stopOpacity={0.3} />
            <stop offset="100%" stopColor="#e50914" stopOpacity={0} />
          </linearGradient>
        </defs>
      </AreaChart>
    </ResponsiveContainer>
  );

  const renderPieChart = () => {
    const pieData = safeData.slice(0, 10);
    const total = pieData.reduce((s, r) => s + (Number(r[yKey]) || 0), 0);
    return (
      <ResponsiveContainer width="100%" height={400}>
        <PieChart>
          <Pie data={pieData} dataKey={yKey} nameKey={xKey} cx="50%" cy="50%" outerRadius={150} innerRadius={80}
            paddingAngle={3} label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
            labelLine={{ stroke: '#475569' }}>
            {pieData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="#141414" strokeWidth={2} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ color: '#94a3b8', paddingTop: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    );
  };

  const renderTable = () => {
    if (!safeData.length) return null;
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-dark-700">
              {columns.map((col) => (
                <th key={col} className="px-4 py-3 text-left text-dark-400 font-medium uppercase text-xs tracking-wider">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {safeData.slice(0, 100).map((row, i) => (
              <tr key={i} className="border-b border-dark-800 hover:bg-dark-800/50 transition-colors">
                {columns.map((col) => (
                  <td key={col} className="px-4 py-3 text-dark-200">
                    {typeof row[col] === 'number' ? formatNumber(row[col]) : (row[col] != null ? String(row[col]) : '—')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {safeData.length > 100 && (
          <p className="text-dark-500 text-sm text-center py-3">
            Showing 100 of {safeData.length} rows
          </p>
        )}
      </div>
    );
  };

  const renderChart = () => {
    switch (chartType) {
      case 'bar': return renderBarChart();
      case 'line': return renderLineChart();
      case 'area': return renderAreaChart();
      case 'pie': return renderPieChart();
      default: return renderTable();
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="glass-card p-6"
    >
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-dark-100 flex items-center gap-2">
          {getChartIcon()}
          {title}
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-dark-500">{safeData.length} rows</span>
          <span className="text-xs px-3 py-1 rounded-full bg-dark-700 text-dark-400 uppercase tracking-wider">
            {chartType}
          </span>
        </div>
      </div>

      <div className="min-h-[400px]">
        {renderChart()}
      </div>

      {chartType !== 'table' && safeData.length > 0 && (
        <div className="mt-6 pt-6 border-t border-dark-700">
          <h4 className="text-sm font-medium text-dark-400 mb-3">Raw Data</h4>
          {renderTable()}
        </div>
      )}
    </motion.div>
  );
};

export default ChartDisplay;
