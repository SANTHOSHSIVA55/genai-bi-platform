import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Table2, Search, ChevronDown, ChevronUp, ArrowUpDown, Database,
  Loader2, ChevronsLeft, ChevronsRight, ChevronLeft, ChevronRight,
  Hash, Tag, Calendar, Type, ToggleLeft, KeyRound, AlertCircle
} from 'lucide-react';
import { getDatasets, getDatasetRows, getDatasetProfile } from '../api/api';

const PAGE_SIZES = [25, 50, 100];

const typeIcon = (type) => {
  switch (type) {
    case 'metric': return <Hash className="w-3 h-3 text-apple-blue" />;
    case 'date': return <Calendar className="w-3 h-3 text-apple-orange" />;
    case 'categorical': return <Tag className="w-3 h-3 text-apple-green" />;
    case 'boolean': return <ToggleLeft className="w-3 h-3 text-apple-purple" />;
    case 'id': return <KeyRound className="w-3 h-3 text-red-400" />;
    default: return <Type className="w-3 h-3 text-dark-400" />;
  }
};

// Memoized row so re-renders from search/sort/page changes only touch the
// cells that actually changed instead of rebuilding every <td>.
const DataRow = React.memo(({ row, columns, rowKey }) => (
  <tr className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors">
    {columns.map((col) => (
      <td key={col} className="px-4 py-3 text-dark-200 whitespace-nowrap max-w-[300px] truncate">
        {row[col] == null ? <span className="text-dark-600">NULL</span> : String(row[col])}
      </td>
    ))}
  </tr>
));

// Search lives in its own component so typing re-renders only this input; the
// 300ms debounce then notifies the parent, which refetches rows.
const SearchInput = ({ onDebouncedChange }) => {
  const [search, setSearch] = useState('');
  const timerRef = useRef(null);
  useEffect(() => () => clearTimeout(timerRef.current), []);
  const onChange = (e) => {
    const v = e.target.value;
    setSearch(v);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onDebouncedChange(v), 300);
  };
  return (
    <div className="relative flex-1">
      <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-500" />
      <input
        type="text"
        value={search}
        onChange={onChange}
        placeholder="Search across all columns..."
        className="input-field pl-10"
      />
    </div>
  );
};

const DataExplorer = () => {
  const navigate = useNavigate();
  const [datasets, setDatasets] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sortBy, setSortBy] = useState('');
  const [sortDir, setSortDir] = useState('asc');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [rows, setRows] = useState([]);
  const [columns, setColumns] = useState([]);
  const [total, setTotal] = useState(0);
  const [rowCount, setRowCount] = useState(0);
  const [uniqueRatio, setUniqueRatio] = useState({});
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getDatasets()
      .then((res) => {
        if (cancelled) return;
        const ds = Array.isArray(res.data) ? res.data : (res.data?.datasets || []);
        setDatasets(ds);
        if (ds.length > 0) setSelectedId((cur) => cur || ds[0].id);
      })
      .catch(() => { if (!cancelled) setError('Unable to load datasets.'); });
    return () => { cancelled = true; };
  }, []);

  // Reset pagination when the dataset or page size changes.
  const resetToFirstPage = useCallback(() => setPage(1), []);

  // Switching datasets clears any stale search term (the input remounts too).
  useEffect(() => { setDebouncedSearch(''); }, [selectedId]);

  useEffect(() => { resetToFirstPage(); }, [selectedId, debouncedSearch, pageSize, resetToFirstPage]);

  // Load the page of rows from the server.
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    setLoading(true);
    const params = {
      page,
      page_size: pageSize,
      ...(sortBy ? { sort_by: sortBy, sort_dir: sortDir } : {}),
      ...(debouncedSearch ? { search: debouncedSearch } : {}),
    };
    getDatasetRows(selectedId, params)
      .then((res) => {
        if (cancelled) return;
        setRows(res.data.rows || []);
        setColumns(res.data.columns || []);
        setTotal(res.data.total ?? 0);
        setRowCount(res.data.row_count ?? 0);
        setUniqueRatio(res.data.unique_ratio || {});
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setRows([]);
        const detail = err.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Failed to load dataset rows.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedId, page, pageSize, sortBy, sortDir, debouncedSearch]);

  // Column profiling metadata for the sidebar.
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    getDatasetProfile(selectedId)
      .then((res) => { if (!cancelled) setProfile(res.data); })
      .catch(() => { if (!cancelled) setProfile(null); });
    return () => { cancelled = true; };
  }, [selectedId]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const pageStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const pageEnd = Math.min(total, page * pageSize);

  const handleSort = (col) => {
    if (sortBy === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(col);
      setSortDir('asc');
    }
  };

  const profileCols = useMemo(() => {
    const meta = profile?.overview?.columns || [];
    if (!meta.length) return [];
    const byName = Object.fromEntries(meta.map((c) => [c.name, c]));
    return columns.map((name) => ({
      name,
      ...(byName[name] || {}),
      unique_ratio: uniqueRatio[name] != null ? uniqueRatio[name] : null,
    }));
  }, [columns, profile, uniqueRatio]);

  const selectedDs = datasets.find((d) => d.id === selectedId);

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
      >
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Table2 className="w-6 h-6 text-primary-400" />
            Data Explorer
          </h1>
          <p className="text-dark-400 text-sm mt-0.5">
            Browse, search, sort and profile your raw data
          </p>
        </div>
        {selectedDs && (
          <span className="text-xs px-3 py-1 rounded-full bg-dark-700/50 text-dark-400">
            {selectedDs.name} &middot; {rowCount.toLocaleString()} rows &middot; {columns.length} cols
          </span>
        )}
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="glass-card p-5 flex flex-col lg:flex-row gap-4"
      >
        <div className="relative lg:w-80 flex-shrink-0">
          <Database className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-500" />
          <select
            value={selectedId}
            onChange={(e) => { setSelectedId(e.target.value); setSortBy(''); }}
            className="input-field pl-10 appearance-none cursor-pointer"
            aria-label="Select dataset"
          >
            {datasets.length === 0 && <option value="">No datasets yet</option>}
            {datasets.map((ds) => (
              <option key={ds.id} value={ds.id}>
                {ds.name} ({ds.row_count.toLocaleString()} rows)
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-dark-400 pointer-events-none" />
        </div>

        <SearchInput key={selectedId || 'none'} onDebouncedChange={setDebouncedSearch} />

        {selectedDs && (
          <button
            onClick={() => navigate('/dashboard', { state: { question: 'Analyze this dataset and give me a complete business summary', datasetId: selectedId } })}
            className="btn-primary text-sm flex items-center gap-2 flex-shrink-0"
          >
            Analyze this data
          </button>
        )}
      </motion.div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-3 p-4 rounded-apple-lg bg-amber-500/8 border border-amber-500/15 text-amber-300"
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <p className="text-sm">{error}</p>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid lg:grid-cols-4 gap-6 items-start">
        <div className="lg:col-span-3 space-y-4">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card overflow-hidden"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.05]">
              <h3 className="text-sm font-semibold text-dark-200 flex items-center gap-2">
                <Table2 className="w-4 h-4 text-primary-400" />
                {debouncedSearch ? `Search results for "${debouncedSearch}"` : 'Data rows'}
              </h3>
              {loading && <Loader2 className="w-4 h-4 text-primary-400 animate-spin" />}
            </div>

            {rows.length === 0 && !loading ? (
              <div className="p-10 text-center">
                <p className="text-dark-500 text-sm">
                  {debouncedSearch ? 'No rows match your search.' : 'No rows to display.'}
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/[0.06]">
                      {columns.map((col) => {
                        const active = sortBy === col;
                        return (
                          <th key={col}>
                            <button
                              onClick={() => handleSort(col)}
                              className="w-full px-4 py-3 text-left text-dark-400 font-medium uppercase text-xs tracking-wider hover:text-dark-200 transition-colors flex items-center gap-1.5"
                            >
                              <span className="truncate">{col}</span>
                              {active ? (
                                sortDir === 'asc' ? <ChevronUp className="w-3 h-3 text-primary-400 flex-shrink-0" /> : <ChevronDown className="w-3 h-3 text-primary-400 flex-shrink-0" />
                              ) : (
                                <ArrowUpDown className="w-3 h-3 opacity-40 flex-shrink-0" />
                              )}
                            </button>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td colSpan={columns.length}>
                          <div className="p-8 text-center">
                            <div className="w-6 h-6 rounded-full border-2 border-primary-500 border-t-transparent animate-spin mx-auto" />
                          </div>
                        </td>
                      </tr>
                    ) : (
                      rows.map((row, i) => (
                        <DataRow
                          key={row[columns[0]] != null ? `${String(row[columns[0]])}-${i}` : i}
                          row={row}
                          columns={columns}
                        />
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-5 py-4 border-t border-white/[0.05]">
              <div className="flex items-center gap-2 text-xs text-dark-500">
                <span>
                  Showing {pageStart}&ndash;{pageEnd} of {total.toLocaleString()} rows
                </span>
                <div className="flex items-center gap-1 ml-3">
                  <select
                    value={pageSize}
                    onChange={(e) => setPageSize(Number(e.target.value))}
                    className="bg-dark-800 border border-white/[0.06] rounded px-1.5 py-1 text-xs text-dark-300 cursor-pointer"
                    aria-label="Rows per page"
                  >
                    {PAGE_SIZES.map((n) => (
                      <option key={n} value={n}>{n} / page</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage(1)}
                  disabled={page <= 1}
                  className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-dark-300 border border-white/[0.04] disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="First page"
                >
                  <ChevronsLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setPage((p) => p - 1)}
                  disabled={page <= 1}
                  className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-dark-300 border border-white/[0.04] disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Previous page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="px-3 py-1.5 text-xs text-dark-300">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page >= totalPages}
                  className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-dark-300 border border-white/[0.04] disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Next page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setPage(totalPages)}
                  disabled={page >= totalPages}
                  className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-dark-300 border border-white/[0.04] disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Last page"
                >
                  <ChevronsRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </motion.div>
        </div>

        <div className="space-y-4">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.12 }}
            className="glass-card p-5"
          >
            <h3 className="text-sm font-semibold text-dark-200 mb-4 flex items-center gap-2">
              <Database className="w-4 h-4 text-primary-400" />
              Column Profile
            </h3>
            {!selectedId ? (
              <p className="text-dark-500 text-sm">Select a dataset to see column profiles.</p>
            ) : profileCols.length === 0 ? (
              <div className="space-y-2">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="h-10 bg-dark-800/40 border border-white/[0.04] rounded-apple animate-pulse" />
                ))}
              </div>
            ) : (
              <div className="space-y-2.5">
                {profileCols.map((col) => (
                  <div key={col.name} className="p-3 rounded-apple bg-dark-800/40 border border-white/[0.04]">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-dark-200 text-sm font-medium truncate flex items-center gap-1.5 min-w-0">
                        {typeIcon(col.type)}
                        <span className="truncate">{col.name}</span>
                      </p>
                      <span className="text-[10px] uppercase tracking-wider text-dark-500 flex-shrink-0">
                        {col.type || col.dtype || 'unknown'}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-1.5 text-[11px] text-dark-500">
                      <span>{col.unique != null ? `${col.unique.toLocaleString()} unique` : '\u2014'}</span>
                      <span>
                        {col.missing != null
                          ? `${col.missing.toLocaleString()} missing`
                          : '\u2014'}
                      </span>
                      {col.unique_ratio != null && (
                        <span>{Math.round(col.unique_ratio * 100)}% distinct</span>
                      )}
                    </div>
                    {col.sample_values?.length > 0 && (
                      <p className="mt-1.5 text-[11px] text-dark-600 truncate">
                        e.g. {col.sample_values.slice(0, 3).map((v) => String(v)).join(' \u00b7 ')}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
};

export default DataExplorer;
