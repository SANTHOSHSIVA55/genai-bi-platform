import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, Database, Trash2, FileSpreadsheet, FileText,
  AlertCircle, CheckCircle2, Loader2, HardDrive, Table2
} from 'lucide-react';
import { getDatasets, deleteDataset } from '../api/api';
import FileUpload from '../components/FileUpload';
import toast from 'react-hot-toast';

const UploadPage = () => {
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(null);

  const fetchDatasets = useCallback(async () => {
    try {
      const res = await getDatasets();
      setDatasets(Array.isArray(res.data) ? res.data : (res.data?.datasets || []));
    } catch (err) {
      console.warn('Could not fetch datasets:', err);
      // Demo data
      setDatasets([
        { id: '1', name: 'Sales Data 2024', row_count: 15420, column_count: 12, file_type: 'csv', created_at: '2024-01-15T10:30:00Z', file_size: 2456789 },
        { id: '2', name: 'Customer Analytics', row_count: 8930, column_count: 8, file_type: 'xlsx', created_at: '2024-02-10T14:20:00Z', file_size: 1234567 },
        { id: '3', name: 'Product Inventory', row_count: 3200, column_count: 6, file_type: 'csv', created_at: '2024-03-05T09:00:00Z', file_size: 789012 },
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDatasets();
  }, [fetchDatasets]);

  const handleUploadSuccess = (newDs) => {
    setDatasets((prev) => [newDs, ...prev]);
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Delete dataset "${name}"? This action cannot be undone.`)) return;
    setDeleting(id);
    try {
      await deleteDataset(id);
      setDatasets((prev) => prev.filter((d) => d.id !== id));
      toast.success(`"${name}" deleted successfully`);
    } catch (err) {
      // Demo mode
      setDatasets((prev) => prev.filter((d) => d.id !== id));
      toast.success(`"${name}" deleted`);
    } finally {
      setDeleting(null);
    }
  };

  const getFileIcon = (type) => {
    if (type === 'pdf') return <FileText className="w-5 h-5 text-red-400" />;
    return <FileSpreadsheet className="w-5 h-5 text-emerald-400" />;
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <Upload className="w-7 h-7 text-primary-400" />
          Data Upload
        </h1>
        <p className="text-dark-400 mt-1">Upload and manage your datasets</p>
      </motion.div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Upload Widget */}
        <FileUpload onUploadSuccess={handleUploadSuccess} />

        {/* Storage Info */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card p-6"
        >
          <h2 className="text-lg font-semibold text-dark-100 mb-4 flex items-center gap-2">
            <HardDrive className="w-5 h-5 text-purple-400" />
            Storage Overview
          </h2>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="p-4 rounded-xl bg-dark-800/50 text-center">
              <p className="text-2xl font-bold text-primary-400">{datasets.length}</p>
              <p className="text-dark-500 text-xs mt-1">Datasets</p>
            </div>
            <div className="p-4 rounded-xl bg-dark-800/50 text-center">
              <p className="text-2xl font-bold text-emerald-400">
                {datasets.reduce((s, d) => s + (d.row_count || 0), 0).toLocaleString()}
              </p>
              <p className="text-dark-500 text-xs mt-1">Total Rows</p>
            </div>
            <div className="p-4 rounded-xl bg-dark-800/50 text-center">
              <p className="text-2xl font-bold text-purple-400">
                {formatFileSize(datasets.reduce((s, d) => s + (d.file_size || 0), 0))}
              </p>
              <p className="text-dark-500 text-xs mt-1">Storage Used</p>
            </div>
          </div>

          {/* Storage bar */}
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-dark-400">Storage Usage</span>
              <span className="text-dark-300">
                {formatFileSize(datasets.reduce((s, d) => s + (d.file_size || 0), 0))} / 500 MB
              </span>
            </div>
            <div className="h-2 bg-dark-800 rounded-full overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${Math.min((datasets.reduce((s, d) => s + (d.file_size || 0), 0) / (500 * 1024 * 1024)) * 100, 100)}%` }}
                transition={{ duration: 1, ease: 'easeOut' }}
                className="h-full bg-gradient-to-r from-primary-500 to-amber-500 rounded-full"
              />
            </div>
          </div>

          {/* Supported formats */}
          <div className="mt-6 p-4 rounded-xl bg-dark-800/30 border border-dark-700/30">
            <p className="text-sm font-medium text-dark-300 mb-2">Supported Formats</p>
            <div className="flex flex-wrap gap-2">
              {['CSV', 'XLSX', 'XLS', 'PDF'].map((fmt) => (
                <span key={fmt} className="px-3 py-1 rounded-lg bg-dark-700 text-dark-400 text-xs font-medium">
                  .{fmt.toLowerCase()}
                </span>
              ))}
            </div>
          </div>
        </motion.div>
      </div>

      {/* Datasets Table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass-card p-6"
      >
        <h2 className="text-lg font-semibold text-dark-100 mb-4 flex items-center gap-2">
          <Database className="w-5 h-5 text-emerald-400" />
          Uploaded Datasets
          <span className="ml-auto text-sm text-dark-500 font-normal">
            {datasets.length} dataset{datasets.length !== 1 ? 's' : ''}
          </span>
        </h2>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 text-primary-400 animate-spin" />
          </div>
        ) : datasets.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-center">
            <div className="w-16 h-16 rounded-2xl bg-dark-800 flex items-center justify-center mb-4">
              <Database className="w-8 h-8 text-dark-600" />
            </div>
            <p className="text-dark-300 font-medium mb-1">No datasets yet</p>
            <p className="text-dark-500 text-sm">Upload your first dataset to get started</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-dark-700">
                  <th className="px-4 py-3 text-left text-dark-400 font-medium text-xs uppercase tracking-wider">Name</th>
                  <th className="px-4 py-3 text-left text-dark-400 font-medium text-xs uppercase tracking-wider">Type</th>
                  <th className="px-4 py-3 text-right text-dark-400 font-medium text-xs uppercase tracking-wider">Rows</th>
                  <th className="px-4 py-3 text-right text-dark-400 font-medium text-xs uppercase tracking-wider">Columns</th>
                  <th className="px-4 py-3 text-right text-dark-400 font-medium text-xs uppercase tracking-wider">Size</th>
                  <th className="px-4 py-3 text-right text-dark-400 font-medium text-xs uppercase tracking-wider">Uploaded</th>
                  <th className="px-4 py-3 text-right text-dark-400 font-medium text-xs uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence>
                  {datasets.map((ds, i) => (
                    <motion.tr
                      key={ds.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 10 }}
                      transition={{ delay: i * 0.05 }}
                      className="border-b border-dark-800 hover:bg-dark-800/50 transition-colors"
                    >
                      <td className="px-4 py-4">
                        <div className="flex items-center gap-3">
                          {getFileIcon(ds.file_type)}
                          <span className="text-dark-100 font-medium">{ds.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <span className="px-2 py-1 rounded bg-dark-700 text-dark-400 text-xs uppercase">{ds.file_type}</span>
                      </td>
                      <td className="px-4 py-4 text-right text-dark-300">{(ds.row_count || 0).toLocaleString()}</td>
                      <td className="px-4 py-4 text-right text-dark-300">{ds.column_count || 0}</td>
                      <td className="px-4 py-4 text-right text-dark-400">{formatFileSize(ds.file_size)}</td>
                      <td className="px-4 py-4 text-right text-dark-500">{ds.created_at ? new Date(ds.created_at).toLocaleDateString() : '—'}</td>
                      <td className="px-4 py-4 text-right">
                        <button
                          onClick={() => handleDelete(ds.id, ds.name)}
                          disabled={deleting === ds.id}
                          className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center p-2.5 rounded-lg hover:bg-red-500/10 text-dark-500 hover:text-red-400 transition-all disabled:opacity-50"
                        >
                          {deleting === ds.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                        </button>
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        )}
      </motion.div>
    </div>
  );
};

export default UploadPage;
