import React, { useState, useEffect, useCallback, useMemo, useDeferredValue } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  History, Search, Clock, MessageSquare, Database,
  ChevronDown, ChevronUp, Loader2, Code2, ArrowRight,
  Calendar, Filter, AlertCircle, Trash2, Eraser, Copy,
  ChevronLeft, ChevronRight
} from 'lucide-react';
import { getQueryHistory, deleteHistoryEntry, clearQueryHistory } from '../api/api';
import toast from 'react-hot-toast';

const PAGE_SIZE = 50;

const HistoryPage = () => {
  const navigate = useNavigate();
  const [queries, setQueries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [sortOrder, setSortOrder] = useState('desc');
  const [page, setPage] = useState(1);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await getQueryHistory();
      const data = Array.isArray(res.data) ? res.data : (res.data?.queries || []);
      setQueries(data);
      setFetchError(null);
    } catch (err) {
      console.warn('Could not fetch history:', err);
      const detail = err.response?.data?.detail;
      setFetchError(typeof detail === 'string' ? detail : 'Unable to connect to the server.');
      setQueries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // Deferred search keeps the input responsive: filtering/sorting run in the
  // background instead of blocking every keystroke.
  const deferredSearch = useDeferredValue(search);

  const filtered = useMemo(() => {
    const term = deferredSearch.toLowerCase();
    return queries
      .filter((q) =>
        !term ||
        q.question?.toLowerCase().includes(term) ||
        q.dataset_name?.toLowerCase().includes(term)
      )
      .sort((a, b) => {
        const da = new Date(a.created_at);
        const db = new Date(b.created_at);
        return sortOrder === 'desc' ? db - da : da - db;
      });
  }, [queries, deferredSearch, sortOrder]);

  // Reset to the first page whenever the visible set changes.
  useEffect(() => { setPage(1); }, [deferredSearch, sortOrder]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visible = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, page]);

  // Formatted relative timestamps are computed once per history entry instead
  // of rebuilding two Date objects per row on every render.
  const timeText = useMemo(() => {
    const map = {};
    const now = Date.now();
    for (const q of queries) {
      const date = new Date(q.created_at);
      const diff = now - date.getTime();
      if (diff < 60000) map[q.id] = 'Just now';
      else if (diff < 3600000) map[q.id] = `${Math.floor(diff / 60000)}m ago`;
      else if (diff < 86400000) map[q.id] = `${Math.floor(diff / 3600000)}h ago`;
      else if (diff < 604800000) map[q.id] = `${Math.floor(diff / 86400000)}d ago`;
      else map[q.id] = date.toLocaleDateString();
    }
    return map;
  }, [queries]);

  const getChartBadge = (type) => {
    const styles = {
      bar: 'bg-primary-500/10 text-primary-400 border-primary-500/15',
      line: 'bg-apple-orange/10 text-apple-orange border-apple-orange/15',
      pie: 'bg-apple-purple/10 text-apple-purple border-apple-purple/15',
      table: 'bg-dark-700/50 text-dark-400 border-white/[0.05]',
    };
    return styles[type] || styles.table;
  };

  const handleRerun = (q) => {
    navigate('/dashboard', {
      state: { question: q.question, datasetId: q.dataset_id || undefined },
    });
  };

  const handleCopySql = (sql) => {
    navigator.clipboard?.writeText(sql).then(
      () => toast.success('SQL copied to clipboard'),
      () => toast.error('Could not copy SQL')
    );
  };

  const handleDelete = async (q) => {
    try {
      await deleteHistoryEntry(q.id);
      setQueries((prev) => prev.filter((x) => x.id !== q.id));
      toast.success('History entry deleted');
    } catch (err) {
      toast.error('Could not delete history entry');
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm('Delete all query history? This cannot be undone.')) return;
    try {
      await clearQueryHistory();
      setQueries([]);
      toast.success('Query history cleared');
    } catch (err) {
      toast.error('Could not clear query history');
    }
  };

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
      >
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <History className="w-6 h-6 text-primary-400" />
            Query History
          </h1>
          <p className="text-dark-400 text-sm mt-0.5">Browse and re-run your previous queries</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-dark-400">
          <Calendar className="w-4 h-4" />
          {filtered.length} queries total
          {filtered.length > 0 && (
            <button
              onClick={handleClearAll}
              title="Clear all history"
              className="ml-2 px-2.5 py-1 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors text-xs flex items-center gap-1.5"
            >
              <Eraser className="w-3 h-3" />
              Clear all
            </button>
          )}
        </div>
      </motion.div>

      <AnimatePresence>
        {fetchError && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="flex items-center gap-3 p-4 rounded-apple-lg bg-amber-500/8 border border-amber-500/15 text-amber-300"
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <p className="text-sm">{fetchError}</p>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08 }}
        className="flex flex-col sm:flex-row gap-3"
      >
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search queries or datasets..."
            className="input-field pl-10"
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
          <div className="w-14 h-14 rounded-2xl bg-dark-800/60 flex items-center justify-center mb-4 border border-white/[0.04]">
            <MessageSquare className="w-7 h-7 text-dark-500" />
          </div>
          <p className="text-dark-300 font-medium mb-1">
            {search ? 'No matching queries' : 'No queries yet'}
          </p>
          <p className="text-dark-500 text-sm">
            {search ? 'Try a different search term' : 'Go to the Dashboard and ask your first question!'}
          </p>
        </motion.div>
      ) : (
        <div className="space-y-2.5">
          <AnimatePresence>
            {visible.map((q, i) => (
              <motion.div
                key={q.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ delay: Math.min(i * 0.02, 0.3) }}
                className="glass-card-hover overflow-hidden"
              >
                <button
                  onClick={() => setExpandedId(expandedId === q.id ? null : q.id)}
                  className="w-full text-left p-4 flex items-center gap-3"
                >
                  <div className="w-9 h-9 rounded-apple bg-primary-500/8 flex items-center justify-center flex-shrink-0 border border-primary-500/10">
                    <MessageSquare className="w-4 h-4 text-primary-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-dark-100 text-sm font-medium truncate">{q.question}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-dark-500 text-xs flex items-center gap-1">
                        <Database className="w-3 h-3" />
                        {q.dataset_name || 'Unknown Dataset'}
                      </span>
                      <span className="text-dark-500 text-xs flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {timeText[q.id]}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2.5 flex-shrink-0">
                    {q.chart_type && (
                      <span className={`px-2 py-0.5 rounded-lg text-[10px] font-medium border ${getChartBadge(q.chart_type)}`}>
                        {q.chart_type}
                      </span>
                    )}
                    {q.row_count != null && (
                      <span className="text-dark-500 text-xs">{q.row_count} rows</span>
                    )}
                    <ChevronDown className={`w-3.5 h-3.5 text-dark-500 transition-transform ${expandedId === q.id ? 'rotate-180' : ''}`} />
                  </div>
                </button>

                <AnimatePresence>
                  {expandedId === q.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-4 pb-4 pt-0 border-t border-white/[0.05]">
                        {q.generated_sql && (
                          <div className="mt-3">
                            <p className="text-xs font-medium text-dark-400 mb-1.5 flex items-center gap-1">
                              <Code2 className="w-3 h-3" />
                              Generated SQL
                            </p>
                            <pre className="text-sm text-dark-300 bg-dark-950/50 p-3 rounded-apple overflow-x-auto font-mono border border-white/[0.04]">
                              {q.generated_sql}
                            </pre>
                          </div>
                        )}
                        <div className="flex gap-3 mt-3 flex-wrap">
                          <button
                            onClick={() => handleRerun(q)}
                            disabled={!q.dataset_id}
                            className="btn-primary text-xs flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            Re-run Query
                            <ArrowRight className="w-3.5 h-3.5" />
                          </button>
                          {q.generated_sql && (
                            <button
                              onClick={() => handleCopySql(q.generated_sql)}
                              className="btn-secondary text-xs flex items-center gap-2"
                            >
                              <Copy className="w-3.5 h-3.5" />
                              Copy SQL
                            </button>
                          )}
                          <button
                            onClick={() => handleDelete(q)}
                            className="text-xs flex items-center gap-2 px-3 py-2 rounded-apple bg-red-500/8 border border-red-500/15 text-red-400 hover:bg-red-500/15 transition-colors ml-auto"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            Delete
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            ))}
          </AnimatePresence>

          {pageCount > 1 && (
            <div className="flex items-center justify-between gap-3 pt-2">
              <span className="text-xs text-dark-500">
                Page {page} of {pageCount} &middot; {filtered.length} queries
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-dark-300 border border-white/[0.04] disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Previous page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                  disabled={page >= pageCount}
                  className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-dark-300 border border-white/[0.04] disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Next page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default HistoryPage;
