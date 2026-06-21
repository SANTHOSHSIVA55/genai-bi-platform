import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  History, Search, Trash2, Clock, MessageSquare, Database,
  ChevronDown, ChevronUp, Loader2, Code2, ArrowRight,
  Calendar, Filter
} from 'lucide-react';
import { getQueryHistory } from '../api/api';
import toast from 'react-hot-toast';

const HistoryPage = () => {
  const [queries, setQueries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [sortOrder, setSortOrder] = useState('desc');

  const fetchHistory = useCallback(async () => {
    try {
      const res = await getQueryHistory();
      const data = Array.isArray(res.data) ? res.data : (res.data?.queries || []);
      setQueries(data);
    } catch (err) {
      console.warn('Could not fetch history:', err);
      // Demo data
      setQueries([
        {
          id: '1',
          question: 'Show me the top 10 products by total revenue',
          dataset_name: 'Sales Data 2024',
          created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
          generated_sql: 'SELECT product_name, SUM(revenue) as total_revenue FROM sales GROUP BY product_name ORDER BY total_revenue DESC LIMIT 10;',
          chart_type: 'bar',
          row_count: 10,
        },
        {
          id: '2',
          question: 'What is the average order value per region?',
          dataset_name: 'Customer Analytics',
          created_at: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
          generated_sql: 'SELECT region, AVG(order_value) as avg_order_value FROM customers GROUP BY region ORDER BY avg_order_value DESC;',
          chart_type: 'bar',
          row_count: 5,
        },
        {
          id: '3',
          question: 'Show monthly sales trend for the last 12 months',
          dataset_name: 'Sales Data 2024',
          created_at: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
          generated_sql: "SELECT DATE_TRUNC('month', sale_date) as month, SUM(revenue) as total FROM sales WHERE sale_date >= NOW() - INTERVAL '12 months' GROUP BY month ORDER BY month;",
          chart_type: 'line',
          row_count: 12,
        },
        {
          id: '4',
          question: 'What percentage of revenue comes from each category?',
          dataset_name: 'Product Inventory',
          created_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
          generated_sql: 'SELECT category, SUM(revenue) as total, ROUND(SUM(revenue) * 100.0 / (SELECT SUM(revenue) FROM products), 1) as pct FROM products GROUP BY category ORDER BY total DESC;',
          chart_type: 'pie',
          row_count: 8,
        },
        {
          id: '5',
          question: 'List the bottom 5 performing SKUs',
          dataset_name: 'Product Inventory',
          created_at: new Date(Date.now() - 1000 * 60 * 60 * 48).toISOString(),
          generated_sql: 'SELECT sku, product_name, units_sold, revenue FROM products ORDER BY revenue ASC LIMIT 5;',
          chart_type: 'table',
          row_count: 5,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const filtered = queries
    .filter((q) =>
      q.question?.toLowerCase().includes(search.toLowerCase()) ||
      q.dataset_name?.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      const da = new Date(a.created_at);
      const db = new Date(b.created_at);
      return sortOrder === 'desc' ? db - da : da - db;
    });

  const formatTime = (iso) => {
    const date = new Date(iso);
    const now = new Date();
    const diff = now - date;
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;
    return date.toLocaleDateString();
  };

  const getChartBadge = (type) => {
    const styles = {
      bar: 'bg-primary-500/10 text-primary-500 border-primary-500/20',
      line: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
      pie: 'bg-rose-500/10 text-rose-500 border-rose-500/20',
      table: 'bg-dark-700 text-dark-400 border-dark-600',
    };
    return styles[type] || styles.table;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
      >
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <History className="w-7 h-7 text-primary-400" />
            Query History
          </h1>
          <p className="text-dark-400 mt-1">Browse and re-run your previous queries</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-dark-400">
          <Calendar className="w-4 h-4" />
          {filtered.length} queries total
        </div>
      </motion.div>

      {/* Search & Filter */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex flex-col sm:flex-row gap-3"
      >
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search queries or datasets..."
            className="input-field pl-12"
          />
        </div>
        <button
          onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
          className="btn-secondary flex items-center gap-2 text-sm"
        >
          <Filter className="w-4 h-4" />
          {sortOrder === 'desc' ? 'Newest First' : 'Oldest First'}
          {sortOrder === 'desc' ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </button>
      </motion.div>

      {/* Query List */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 text-primary-400 animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center py-20 text-center"
        >
          <div className="w-16 h-16 rounded-2xl bg-dark-800 flex items-center justify-center mb-4">
            <MessageSquare className="w-8 h-8 text-dark-600" />
          </div>
          <p className="text-dark-300 font-medium mb-1">
            {search ? 'No matching queries' : 'No queries yet'}
          </p>
          <p className="text-dark-500 text-sm">
            {search ? 'Try a different search term' : 'Go to the Dashboard and ask your first question!'}
          </p>
        </motion.div>
      ) : (
        <div className="space-y-3">
          <AnimatePresence>
            {filtered.map((q, i) => (
              <motion.div
                key={q.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ delay: i * 0.03 }}
                className="glass-card-hover overflow-hidden"
              >
                {/* Main row */}
                <button
                  onClick={() => setExpandedId(expandedId === q.id ? null : q.id)}
                  className="w-full text-left p-5 flex items-center gap-4"
                >
                  <div className="w-10 h-10 rounded-xl bg-primary-500/10 flex items-center justify-center flex-shrink-0">
                    <MessageSquare className="w-5 h-5 text-primary-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-dark-100 font-medium truncate">{q.question}</p>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-dark-500 text-xs flex items-center gap-1">
                        <Database className="w-3 h-3" />
                        {q.dataset_name || 'Unknown Dataset'}
                      </span>
                      <span className="text-dark-600 text-xs flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatTime(q.created_at)}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    {q.chart_type && (
                      <span className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${getChartBadge(q.chart_type)}`}>
                        {q.chart_type}
                      </span>
                    )}
                    {q.row_count != null && (
                      <span className="text-dark-500 text-xs">{q.row_count} rows</span>
                    )}
                    <ChevronDown className={`w-4 h-4 text-dark-500 transition-transform ${expandedId === q.id ? 'rotate-180' : ''}`} />
                  </div>
                </button>

                {/* Expanded details */}
                <AnimatePresence>
                  {expandedId === q.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-5 pb-5 pt-0 border-t border-dark-700/50">
                        {q.generated_sql && (
                          <div className="mt-4">
                            <p className="text-xs font-medium text-dark-400 mb-2 flex items-center gap-1">
                              <Code2 className="w-3 h-3" />
                              Generated SQL
                            </p>
                            <pre className="text-sm text-dark-300 bg-dark-900 p-4 rounded-xl overflow-x-auto font-mono">
                              {q.generated_sql}
                            </pre>
                          </div>
                        )}
                        <div className="flex gap-3 mt-4">
                          <button className="btn-primary text-sm flex items-center gap-2">
                            Re-run Query
                            <ArrowRight className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
};

export default HistoryPage;
