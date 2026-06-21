import React from 'react';
import { motion } from 'framer-motion';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { BarChart3, TrendingUp, PieChart as PieIcon, Table2 } from 'lucide-react';

const COLORS = [
  '#e50914', '#ff3e4b', '#b81d24', '#ffa00a', '#ff7e8a',
  '#ffc9c9', '#8c141a', '#e5b809', '#f43f5e', '#808080',
];

const ChartDisplay = ({ data, chartConfig }) => {
  if (!data || data.length === 0 || !chartConfig) return null;

  const chartType = chartConfig.chart_type || 'table';
  const xKey = chartConfig.x_axis;
  const yKey = chartConfig.y_axis;
  const title = chartConfig.title || 'Query Results';

  const getChartIcon = () => {
    switch (chartType) {
      case 'bar': return <BarChart3 className="w-5 h-5 text-primary-500" />;
      case 'line': return <TrendingUp className="w-5 h-5 text-amber-500" />;
      case 'pie': return <PieIcon className="w-5 h-5 text-rose-500" />;
      default: return <Table2 className="w-5 h-5 text-dark-400" />;
    }
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-3 shadow-xl">
        <p className="text-dark-300 text-sm font-medium mb-1">{label}</p>
        {payload.map((entry, i) => (
          <p key={i} className="text-sm" style={{ color: entry.color }}>
            {entry.name}: <span className="font-semibold">{typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}</span>
          </p>
        ))}
      </div>
    );
  };

  const renderChart = () => {
    switch (chartType) {
      case 'bar':
        return (
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2f2f2f" />
              <XAxis dataKey={xKey} tick={{ fill: '#808080', fontSize: 12 }} angle={-30} textAnchor="end" />
              <YAxis tick={{ fill: '#808080', fontSize: 12 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ color: '#808080' }} />
              <Bar dataKey={yKey} fill="url(#barGradient)" radius={[6, 6, 0, 0]} />
              <defs>
                <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#e50914" />
                  <stop offset="100%" stopColor="#8c141a" />
                </linearGradient>
              </defs>
            </BarChart>
          </ResponsiveContainer>
        );

      case 'line':
        return (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2f2f2f" />
              <XAxis dataKey={xKey} tick={{ fill: '#808080', fontSize: 12 }} angle={-30} textAnchor="end" />
              <YAxis tick={{ fill: '#808080', fontSize: 12 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ color: '#808080' }} />
              <Line
                type="monotone"
                dataKey={yKey}
                stroke="#e50914"
                strokeWidth={3}
                dot={{ fill: '#e50914', r: 5, strokeWidth: 2, stroke: '#141414' }}
                activeDot={{ r: 8, fill: '#ff3e4b' }}
              />
            </LineChart>
          </ResponsiveContainer>
        );

      case 'pie':
        return (
          <ResponsiveContainer width="100%" height={400}>
            <PieChart>
              <Pie
                data={data.slice(0, 10)}
                dataKey={yKey}
                nameKey={xKey}
                cx="50%"
                cy="50%"
                outerRadius={150}
                innerRadius={80}
                paddingAngle={3}
                label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                labelLine={{ stroke: '#475569' }}
              >
                {data.slice(0, 10).map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ color: '#94a3b8' }} />
            </PieChart>
          </ResponsiveContainer>
        );

      default:
        return renderTable();
    }
  };

  const renderTable = () => {
    if (!data.length) return null;
    const columns = Object.keys(data[0]);
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
            {data.slice(0, 100).map((row, i) => (
              <tr key={i} className="border-b border-dark-800 hover:bg-dark-800/50 transition-colors">
                {columns.map((col) => (
                  <td key={col} className="px-4 py-3 text-dark-200">
                    {row[col] != null ? String(row[col]) : '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {data.length > 100 && (
          <p className="text-dark-500 text-sm text-center py-3">
            Showing 100 of {data.length} rows
          </p>
        )}
      </div>
    );
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
        <span className="text-xs px-3 py-1 rounded-full bg-dark-700 text-dark-400 uppercase tracking-wider">
          {chartType}
        </span>
      </div>
      {renderChart()}

      {/* Always show table below chart */}
      {chartType !== 'table' && data.length > 0 && (
        <div className="mt-6 pt-6 border-t border-dark-700">
          <h4 className="text-sm font-medium text-dark-400 mb-3">Raw Data</h4>
          {renderTable()}
        </div>
      )}
    </motion.div>
  );
};

export default ChartDisplay;
