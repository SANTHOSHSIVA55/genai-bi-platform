import React, { useMemo, useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ScatterChart, Scatter, ZAxis
} from 'recharts';
import {
  BarChart3, TrendingUp, PieChart as PieIcon, AreaChart as AreaChartIcon,
  Table2, Target, ArrowUpDown, Database, Tag, Hash, Maximize2, Minimize2,
  Download, Image as ImageIcon
} from 'lucide-react';

const COLORS = [
  '#ff3b30', '#ff6b6b', '#ff9500', '#ffcc00', '#34c759',
  '#5ac8fa', '#007aff', '#af52de', '#ff2d55', '#8e8e93',
];

// Rendering hundreds of SVG marks per chart point janks low-end machines.
// Categorical charts cap at 60 categories; scatter tolerates more. The raw-data
// table below still shows the full (capped) result set independently.
const CHART_DATA_CAP = 60;
const SCATTER_DATA_CAP = 200;

// Recharts re-animates every series from scratch on each data change unless
// disabled; the entrance animation janks the dashboard exactly when a fresh
// result just mounted, so it is turned off everywhere.
const TICK_STYLE = { fill: '#8e8e93', fontSize: 11, fontFamily: 'Inter, sans-serif' };
const GRID_STYLE = { strokeDasharray: '3 3', stroke: '#2c2c2e' };

const isAnalysisResult = (data, chartType) => {
  if (!data || data.length !== 1 || chartType !== 'kpi') return false;
  const cols = Object.keys(data[0] || {});
  const kpiCols = cols.filter(c => /total|avg_|min_|max_|count|sum|unique/.test(c));
  return kpiCols.length >= 2;
};

const KPI_ICONS = {
  total_records: Database,
  unique: Tag,
  avg: Hash,
  min: Hash,
  max: Hash,
  total: Database,
};

const renderKpiGrid = (data, title, renderValue) => {
  if (!data || data.length === 0) return null;
  const row = data[0];
  const entries = Object.entries(row).filter(([_, v]) => v != null);

  return (
    <div className="space-y-4">
      <p className="text-sm text-dark-400 mb-1">{title}</p>
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {entries.map(([key, val]) => {
          const iconKey = Object.keys(KPI_ICONS).find(k => key.toLowerCase().includes(k));
          const Icon = iconKey ? KPI_ICONS[iconKey] : Hash;
          const displayVal = renderValue(key, val);
          const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
          return (
            <div key={key} className="kpi-card p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] text-dark-400 uppercase tracking-wider truncate">{label}</span>
                <div className="w-7 h-7 rounded-lg bg-primary-500/10 border border-primary-500/15 flex items-center justify-center">
                  <Icon className="w-3.5 h-3.5 text-primary-400" />
                </div>
              </div>
              <p className="text-xl sm:text-2xl font-bold text-white tracking-tight">{displayVal}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const formatNumber = (val) => {
  if (val == null || val === '') return '\u2014';
  if (typeof val === 'string' && isNaN(Number(val))) return val;
  const num = Number(val);
  if (isNaN(num)) return String(val);
  if (Math.abs(num) >= 1e9) return (num / 1e9).toFixed(1) + 'B';
  if (Math.abs(num) >= 1e6) return (num / 1e6).toFixed(1) + 'M';
  if (Math.abs(num) >= 1e3) return (num / 1e3).toFixed(1) + 'K';
  return num % 1 === 0 ? num.toLocaleString() : num.toFixed(2);
};

// Professional money formatting; currency symbol is shown only when the backend
// could determine it from the dataset (e.g. ₹). Otherwise plain 3,983.00.
const makeMoneyFormatter = (currency) => (val) => {
  if (val == null || val === '' || isNaN(Number(val))) return formatNumber(val);
  const num = Number(val);
  const formatted = num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${currency}${formatted}` : formatted;
};

const smartAxisKey = (data, columns, preferred) => {
  if (preferred && columns.includes(preferred)) return preferred;
  if (preferred) {
    const match = columns.find(c => c.toLowerCase() === preferred.toLowerCase());
    if (match) return match;
  }
  return columns[0] || '';
};

/* ───── Custom Tooltip Moved Outside Render to Fix Memory Leaks ───── */
const CustomTooltip = ({ active, payload, label, renderValue }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-dark-800/95 border border-white/[0.08] rounded-apple-lg p-3 shadow-apple max-w-xs backdrop-blur-2xl">
      <p className="text-dark-300 text-sm font-medium mb-1.5 truncate">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-sm flex justify-between gap-4" style={{ color: entry.color }}>
          <span className="truncate">{entry.name}:</span>
          <span className="font-semibold whitespace-nowrap">{renderValue(entry.dataKey, entry.value)}</span>
        </p>
      ))}
    </div>
  );
};

const ChartDisplay = ({ data, chartConfig, intentType, currency, semanticTypes }) => {
  const [selectedChartType, setSelectedChartType] = useState('auto');
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Sync / Reset to auto on query changes
  useEffect(() => {
    setSelectedChartType('auto');
  }, [chartConfig]);

  const safeData = useMemo(() => {
    if (!data || !Array.isArray(data) || data.length === 0) return [];
    return data.filter(row => row && typeof row === 'object');
  }, [data]);

  const autoChartType = chartConfig?.chart_type || 'table';
  const chartType = selectedChartType === 'auto' ? autoChartType : selectedChartType;

  // Chart data is capped independently from the raw table so the SVG stays
  // cheap to render and animate on large result sets. `chartType` must be
  // declared above this memo (TDZ: referencing a later const crashes render).
  const chartData = useMemo(() => {
    const cap = chartType === 'scatter' ? SCATTER_DATA_CAP : CHART_DATA_CAP;
    return safeData.length > cap ? safeData.slice(0, cap) : safeData;
  }, [safeData, chartType]);
  const chartCapped = chartData.length < safeData.length;

  const money = useMemo(() => makeMoneyFormatter(currency), [currency]);

  // Per-column semantic formatting: COUNT results are always plain integers,
  // only genuinely monetary columns get the currency symbol; PERCENTAGE columns
  // get a % suffix; date/text columns pass through.
  const renderValue = useMemo(() => {
    return (col, val) => {
      if (val == null || val === '') return '\u2014';
      if (typeof val === 'number') {
        const st = (semanticTypes || {})[col];
        if (st === 'count') return formatNumber(val);
        if (st === 'percentage') return formatNumber(val) + '%';
        if (st === 'currency') return money(val);
        return currency ? money(val) : formatNumber(val);
      }
      return String(val);
    };
  }, [money, currency, semanticTypes]);

  if (safeData.length === 0 || !chartConfig) return null;

  const columns = useMemo(
    () => (safeData.length > 0 ? Object.keys(safeData[0]) : []),
    [safeData]
  );
  const xKey = useMemo(() => smartAxisKey(safeData, columns, chartConfig.x_axis), [safeData, columns, chartConfig]);
  const yKey = useMemo(() => smartAxisKey(safeData, columns, chartConfig.y_axis), [safeData, columns, chartConfig]);
  const title = chartConfig.title || 'Query Results';

  const numericCols = useMemo(
    () => columns.filter(c => typeof safeData[0]?.[c] === 'number'),
    [columns, safeData]
  );
  const hasMultiY = numericCols.length > 1 && chartType !== 'pie';

  const isRanking = intentType === 'ranking' || columns.length === 2;

  const axisTick = useMemo(() => {
    return (v) => {
      const col = numericCols[0] || yKey;
      const st = (semanticTypes || {})[col];
      if (typeof v === 'number') {
        if (st === 'count') return formatNumber(v);
        if (st === 'percentage') return formatNumber(v) + '%';
        if (st === 'currency') return money(v);
        return currency ? currency + formatNumber(v) : formatNumber(v);
      }
      if (st === 'date' && typeof v === 'string') {
        const d = new Date(v);
        if (!isNaN(d.getTime())) {
          const month = d.toLocaleString('en', { month: 'short' });
          return d.getFullYear() === new Date().getFullYear()
            ? month
            : `${month} '${String(d.getFullYear()).slice(2)}`;
        }
      }
      return String(v);
    };
  }, [numericCols, yKey, semanticTypes, money, currency]);

  // Multi-KPI analysis result grid
  if (isAnalysisResult(safeData, chartType)) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="glass-card p-6"
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-dark-100 flex items-center gap-2">
            <Target className="w-5 h-5 text-primary-400" />
            {title}
          </h3>
          <span className="text-xs px-3 py-1 rounded-full bg-dark-700/50 text-dark-400 uppercase tracking-wider">Analysis</span>
        </div>
        {renderKpiGrid(safeData, chartConfig.description || '', renderValue)}
      </motion.div>
    );
  }

  // KPI Card (single value)
  if (chartType === 'kpi') {
    const kpiValue = safeData[0]?.[xKey] ?? safeData[0]?.[yKey] ?? 0;
    const kpiLabel = chartConfig.title || 'Result';
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="kpi-card"
      >
        <div className="flex items-start justify-between mb-2">
          <div className="kpi-label">{kpiLabel}</div>
          <div className="w-10 h-10 rounded-xl bg-primary-500/10 border border-primary-500/20 flex items-center justify-center">
            <Target className="w-5 h-5 text-primary-400" />
          </div>
        </div>
        <div className="kpi-value">{renderValue(xKey, kpiValue)}</div>
        <div className="mt-2 flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-apple-green" />
          <span className="text-[11px] text-dark-500">
            {safeData.length} row{safeData.length !== 1 ? 's' : ''}
          </span>
        </div>
      </motion.div>
    );
  }

  const getChartIcon = () => {
    switch (chartType) {
      case 'bar': return isRanking ? <ArrowUpDown className="w-5 h-5 text-primary-500" /> : <BarChart3 className="w-5 h-5 text-primary-500" />;
      case 'line': return <TrendingUp className="w-5 h-5 text-apple-orange" />;
      case 'area': return <AreaChartIcon className="w-5 h-5 text-apple-green" />;
      case 'pie': return <PieIcon className="w-5 h-5 text-apple-purple" />;
      case 'donut': return <PieIcon className="w-5 h-5 text-apple-blue" />;
      default: return <Table2 className="w-5 h-5 text-dark-400" />;
    }
  };

  const renderBarChart = () => {
    const isHorizontal = isRanking && chartData.length <= 20;

    if (isHorizontal) {
      const sorted = [...chartData].sort((a, b) => (b[yKey] || 0) - (a[yKey] || 0));
      return (
        <ResponsiveContainer width="100%" height={Math.max(200, sorted.length * 36)}>
          <BarChart data={sorted} layout="vertical" margin={{ top: 10, right: 30, left: 100, bottom: 10 }}>
            <CartesianGrid {...GRID_STYLE} horizontal={false} />
            <XAxis type="number" tick={TICK_STYLE} tickFormatter={axisTick} />
            <YAxis dataKey={xKey} type="category" tick={TICK_STYLE} width={90} tickLine={false} axisLine={false} />
            <Tooltip content={<CustomTooltip renderValue={renderValue} />} />
            <Bar dataKey={yKey} fill="url(#barGrad)" radius={[0, 4, 4, 0]} maxBarSize={24} isAnimationActive={false} />
            <defs>
              <linearGradient id="barGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#ff3b30" />
                <stop offset="100%" stopColor="#c41a1a" />
              </linearGradient>
            </defs>
          </BarChart>
        </ResponsiveContainer>
      );
    }

    return (
      <ResponsiveContainer width="100%" height={400}>
        <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
          <CartesianGrid {...GRID_STYLE} />
          <XAxis dataKey={xKey} tick={TICK_STYLE} angle={chartData.length > 8 ? -35 : 0} textAnchor="end" interval={0} />
          <YAxis tick={TICK_STYLE} tickFormatter={axisTick} />
          <Tooltip content={<CustomTooltip renderValue={renderValue} />} />
          <Legend wrapperStyle={{ color: '#aeaeb2', paddingTop: 12 }} />
          {hasMultiY ? (
            numericCols.map((col, i) => (
              <Bar key={col} dataKey={col} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            ))
          ) : (
            <Bar dataKey={yKey} fill="url(#barGradV)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          )}
          <defs>
            <linearGradient id="barGradV" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ff3b30" />
              <stop offset="100%" stopColor="#c41a1a" />
            </linearGradient>
          </defs>
        </BarChart>
      </ResponsiveContainer>
    );
  };

  const renderLineChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <LineChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
        <CartesianGrid {...GRID_STYLE} />
        <XAxis dataKey={xKey} tick={TICK_STYLE} angle={chartData.length > 8 ? -35 : 0} textAnchor="end" interval={0} />
        <YAxis tick={TICK_STYLE} tickFormatter={axisTick} />
        <Tooltip content={<CustomTooltip renderValue={renderValue} />} />
        <Legend wrapperStyle={{ color: '#aeaeb2', paddingTop: 12 }} />
        {hasMultiY ? (
          numericCols.map((col, i) => (
            <Line key={col} type="monotone" dataKey={col} stroke={COLORS[i % COLORS.length]} strokeWidth={2.5}
              dot={{ fill: COLORS[i % COLORS.length], r: 4, strokeWidth: 2, stroke: '#1c1c1e' }}
              activeDot={{ r: 7, strokeWidth: 2 }} isAnimationActive={false} />
          ))
        ) : (
          <Line type="monotone" dataKey={yKey} stroke="#ff3b30" strokeWidth={3}
            dot={{ fill: '#ff3b30', r: 5, strokeWidth: 2, stroke: '#1c1c1e' }}
            activeDot={{ r: 8, fill: '#ff6b6b', stroke: '#1c1c1e', strokeWidth: 2 }} isAnimationActive={false} />
        )}
      </LineChart>
    </ResponsiveContainer>
  );

  const renderAreaChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <AreaChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
        <CartesianGrid {...GRID_STYLE} />
        <XAxis dataKey={xKey} tick={TICK_STYLE} angle={chartData.length > 8 ? -35 : 0} textAnchor="end" interval={0} />
        <YAxis tick={TICK_STYLE} tickFormatter={axisTick} />
        <Tooltip content={<CustomTooltip renderValue={renderValue} />} />
        <Legend wrapperStyle={{ color: '#aeaeb2', paddingTop: 12 }} />
        {hasMultiY ? (
          numericCols.map((col, i) => (
            <Area key={col} type="monotone" dataKey={col} stroke={COLORS[i % COLORS.length]} fill={COLORS[i % COLORS.length]}
              fillOpacity={0.1} strokeWidth={2.5} isAnimationActive={false} />
          ))
        ) : (
          <Area type="monotone" dataKey={yKey} stroke="#ff3b30" fill="url(#areaGrad)" strokeWidth={3} isAnimationActive={false} />
        )}
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ff3b30" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#ff3b30" stopOpacity={0} />
          </linearGradient>
        </defs>
      </AreaChart>
    </ResponsiveContainer>
  );

  const renderPieChart = (isDonut = false) => {
    const pieData = chartData.slice(0, 10);
    return (
      <ResponsiveContainer width="100%" height={400}>
        <PieChart>
          <Pie data={pieData} dataKey={yKey} nameKey={xKey} cx="50%" cy="50%" outerRadius={150} innerRadius={isDonut ? 80 : 0}
            paddingAngle={3} isAnimationActive={false}
            label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
            labelLine={{ stroke: '#48484a' }}>
            {pieData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="#1c1c1e" strokeWidth={2} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip renderValue={renderValue} />} />
          <Legend wrapperStyle={{ color: '#aeaeb2', paddingTop: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    );
  };

  const renderScatterChart = () => (
    <ResponsiveContainer width="100%" height={400}>
      <ScatterChart margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
        <CartesianGrid {...GRID_STYLE} />
        <XAxis type="category" dataKey={xKey} name={xKey} tick={TICK_STYLE} />
        <YAxis type="number" dataKey={yKey} name={yKey} tick={TICK_STYLE} tickFormatter={axisTick} />
        <Tooltip content={<CustomTooltip renderValue={renderValue} />} />
        <Legend wrapperStyle={{ color: '#aeaeb2', paddingTop: 12 }} />
        <Scatter name={`${yKey} by ${xKey}`} data={chartData} fill="#ff3b30" isAnimationActive={false} />
      </ScatterChart>
    </ResponsiveContainer>
  );

  const renderTable = () => {
    if (!safeData.length) return null;
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/[0.06]">
              {columns.map((col) => (
                <th key={col} className="px-4 py-3 text-left text-dark-400 font-medium uppercase text-xs tracking-wider">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {safeData.slice(0, 100).map((row, i) => (
              <tr key={row[xKey] != null ? `${String(row[xKey])}-${i}` : i} className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                {columns.map((col) => (
                  <td key={col} className="px-4 py-3 text-dark-200">
                    {renderValue(col, row[col])}
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
      case 'pie': return renderPieChart(false);
      case 'donut': return renderPieChart(true);
      case 'scatter': return renderScatterChart();
      default: return renderTable();
    }
  };

  const downloadSvg = () => {
    const svgElement = document.querySelector('.recharts-responsive-container svg');
    if (!svgElement) return;
    const svgString = new XMLSerializer().serializeToString(svgElement);
    const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
    const svgUrl = URL.createObjectURL(svgBlob);
    const downloadLink = document.createElement('a');
    downloadLink.href = svgUrl;
    downloadLink.download = `${title.toLowerCase().replace(/\s+/g, '-')}.svg`;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
    URL.revokeObjectURL(svgUrl);
  };

  const chartTypesList = ['auto', 'bar', 'line', 'area', 'pie', 'donut', 'scatter', 'table'];

  const containerContent = (
    <div className={`flex flex-col h-full ${isFullscreen ? 'bg-dark-900 p-8 w-full h-full' : ''}`}>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h3 className="text-lg font-semibold text-dark-100 flex items-center gap-2">
            {getChartIcon()}
            {title}
          </h3>
          {chartConfig.description && (
            <p className="text-xs text-dark-400 mt-1">{chartConfig.description}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Manual controls buttons */}
          <div className="flex items-center rounded-lg bg-dark-800 p-0.5 border border-white/[0.04] overflow-x-auto max-w-full">
            {chartTypesList.map(type => (
              <button
                key={type}
                onClick={() => setSelectedChartType(type)}
                className={`px-2.5 py-1 text-xs font-medium rounded-md capitalize transition-colors whitespace-nowrap ${
                  chartType === type || (type === 'auto' && selectedChartType === 'auto')
                    ? 'bg-primary-500 text-white shadow-sm'
                    : 'text-dark-400 hover:text-dark-200'
                }`}
              >
                {type}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1">
            {chartType !== 'table' && (
              <button
                onClick={downloadSvg}
                className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-dark-300 border border-white/[0.04]"
                title="Download Chart (SVG)"
              >
                <ImageIcon className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-dark-300 border border-white/[0.04]"
              title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-[400px]">
        {renderChart()}
        {chartCapped && chartType !== 'table' && (
          <p className="text-dark-500 text-xs text-center mt-2">
            Charting the first {chartData.length} of {safeData.length} data points
          </p>
        )}
      </div>

      {chartType !== 'table' && safeData.length > 0 && (
        <div className="mt-6 pt-6 border-t border-white/[0.06]">
          <h4 className="text-sm font-medium text-dark-400 mb-3">Raw Data</h4>
          {renderTable()}
        </div>
      )}
    </div>
  );

  return (
    <>
      {isFullscreen ? (
        <div className="fixed inset-0 z-50 bg-dark-950 flex items-center justify-center p-4">
          <div className="relative w-full h-full max-w-7xl">
            {containerContent}
          </div>
        </div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="glass-card p-6"
        >
          {containerContent}
        </motion.div>
      )}
    </>
  );
};

// Memoized so Dashboard re-renders (history/loading/conversation toggles) do
// not rebuild the full recharts tree when the data props are unchanged.
export default React.memo(ChartDisplay);
