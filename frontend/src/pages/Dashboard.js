import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles, Database, TrendingUp, Clock, RefreshCw,
  AlertCircle, BarChart3, Loader2
} from 'lucide-react';
import { getDatasets, getQueryHistory, executeQuery } from '../api/api';
import { DashboardScene } from '../components/Scene3D';
import KPICards from '../components/KPICards';
import QueryInput from '../components/QueryInput';
import ChartDisplay from '../components/ChartDisplay';
import SummaryPanel from '../components/SummaryPanel';
import toast from 'react-hot-toast';

const Dashboard = () => {
  const [datasets, setDatasets] = useState([]);
  const [queryHistory, setQueryHistory] = useState([]);
  const [queryResult, setQueryResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [dsRes, histRes] = await Promise.all([
        getDatasets().catch(() => ({ data: [] })),
        getQueryHistory().catch(() => ({ data: [] })),
      ]);
      setDatasets(Array.isArray(dsRes.data) ? dsRes.data : (dsRes.data?.datasets || []));
      setQueryHistory(Array.isArray(histRes.data) ? histRes.data : (histRes.data?.queries || []));
      setError(null);
    } catch (err) {
      console.warn('Could not fetch initial data:', err);
      setError('Unable to connect to server. Using demo mode.');
      // Demo data
      setDatasets([
        { id: '1', name: 'Sales Data 2024', row_count: 15420, column_count: 12, file_type: 'csv' },
        { id: '2', name: 'Customer Analytics', row_count: 8930, column_count: 8, file_type: 'xlsx' },
        { id: '3', name: 'Product Inventory', row_count: 3200, column_count: 6, file_type: 'csv' },
      ]);
      setQueryHistory([
        { id: '1', question: 'Show top 10 products by revenue', created_at: new Date().toISOString() },
        { id: '2', question: 'Average sales per region', created_at: new Date().toISOString() },
      ]);
    } finally {
      setInitialLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleQuery = async (queryData) => {
    setLoading(true);
    setQueryResult(null);
    try {
      const res = await executeQuery(queryData);
      setQueryResult(res.data);
      toast.success('Query executed successfully!');
      // Refresh history
      const histRes = await getQueryHistory().catch(() => null);
      if (histRes) {
        setQueryHistory(Array.isArray(histRes.data) ? histRes.data : (histRes.data?.queries || []));
      }
    } catch (err) {
      // If server is unavailable, show demo result
      if (!err.response) {
        const demoResult = {
          data: [
            { product: 'Widget A', revenue: 125000, units: 3200 },
            { product: 'Widget B', revenue: 98000, units: 2800 },
            { product: 'Widget C', revenue: 87000, units: 2100 },
            { product: 'Widget D', revenue: 72000, units: 1900 },
            { product: 'Widget E', revenue: 65000, units: 1700 },
            { product: 'Widget F', revenue: 54000, units: 1400 },
            { product: 'Widget G', revenue: 43000, units: 1100 },
            { product: 'Widget H', revenue: 38000, units: 900 },
          ],
          chart_config: {
            chart_type: 'bar',
            x_axis: 'product',
            y_axis: 'revenue',
            title: `Results for: "${queryData.question}"`,
          },
          generated_sql: `SELECT product, revenue, units FROM sales ORDER BY revenue DESC LIMIT 8;`,
          summary: {
            executive_summary: [
              'Widget A leads with $125,000 in revenue, 28% above the next closest product.',
              'Top 3 products account for 47% of total revenue across all products.',
              'Revenue distribution shows a healthy long-tail with gradual decline.',
            ],
            recommendations: [
              'Consider increasing marketing budget for Widget A to capitalize on its strong performance.',
              'Investigate why Widget G-H have lower conversion — potential supply chain issues.',
              'Bundle lower-performing products with top sellers for cross-sell opportunities.',
            ],
            risks: [
              'High concentration risk: Top 2 products represent 34% of total revenue.',
              'Widget H shows declining trend — monitor closely for potential phase-out.',
            ],
            follow_up_questions: [
              'What is the profit margin for each product?',
              'Show monthly revenue trends for top 5 products',
              'Which regions contribute most to Widget A sales?',
            ],
          },
        };
        setQueryResult(demoResult);
        toast.success('Demo results generated!');
      } else {
        toast.error(err.response?.data?.detail || 'Query failed');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleFollowUp = (question) => {
    if (datasets.length > 0) {
      handleQuery({ question, dataset_id: datasets[0].id });
    }
  };

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
          <p className="text-dark-400 text-sm">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative">
      {/* 3D Background */}
      <div className="fixed inset-0 z-0 opacity-30">
        <DashboardScene />
      </div>

      <div className="relative z-10 space-y-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"
        >
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <Sparkles className="w-7 h-7 text-primary-400" />
              Dashboard
            </h1>
            <p className="text-dark-400 mt-1">Your data intelligence hub</p>
          </div>
          <button
            onClick={fetchData}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </motion.div>

        {/* Connection error banner */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="flex items-center gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300"
            >
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <p className="text-sm">{error}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* KPI Cards */}
        <KPICards datasets={datasets} queryCount={queryHistory.length} />

        {/* Main Grid */}
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Query Section — spans 2 cols */}
          <div className="lg:col-span-2 space-y-6">
            <QueryInput datasets={datasets} onSubmit={handleQuery} loading={loading} />

            {/* Loading state */}
            <AnimatePresence>
              {loading && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="glass-card p-8 flex flex-col items-center gap-4"
                >
                  <div className="relative">
                    <div className="w-16 h-16 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
                    <Sparkles className="w-6 h-6 text-primary-400 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                  </div>
                  <div className="text-center">
                    <p className="text-dark-200 font-medium">AI is analyzing your data...</p>
                    <p className="text-dark-500 text-sm mt-1">Generating insights and visualizations</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Results */}
            {queryResult && (
              <>
                <ChartDisplay data={queryResult.data} chartConfig={queryResult.chart_config} />
                <SummaryPanel
                  summary={queryResult.summary}
                  generatedSql={queryResult.generated_sql}
                  onFollowUp={handleFollowUp}
                />
              </>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Datasets */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="glass-card p-5"
            >
              <h3 className="text-sm font-semibold text-dark-200 mb-4 flex items-center gap-2">
                <Database className="w-4 h-4 text-primary-400" />
                Your Datasets
              </h3>
              <div className="space-y-2">
                {datasets.length === 0 ? (
                  <p className="text-dark-500 text-sm py-4 text-center">No datasets yet. Upload one to get started!</p>
                ) : (
                  datasets.map((ds) => (
                    <div key={ds.id} className="p-3 rounded-xl bg-dark-800/50 hover:bg-dark-800 transition-colors border border-dark-700/30">
                      <p className="text-dark-100 font-medium text-sm">{ds.name}</p>
                      <p className="text-dark-500 text-xs mt-1">
                        {(ds.row_count || 0).toLocaleString()} rows · {ds.column_count || 0} cols
                        <span className="ml-2 px-1.5 py-0.5 rounded bg-dark-700 text-dark-400 uppercase text-[10px]">
                          {ds.file_type}
                        </span>
                      </p>
                    </div>
                  ))
                )}
              </div>
            </motion.div>

            {/* Recent Queries */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="glass-card p-5"
            >
              <h3 className="text-sm font-semibold text-dark-200 mb-4 flex items-center gap-2">
                <Clock className="w-4 h-4 text-amber-400" />
                Recent Queries
              </h3>
              <div className="space-y-2">
                {queryHistory.length === 0 ? (
                  <p className="text-dark-500 text-sm py-4 text-center">No queries yet. Ask your first question!</p>
                ) : (
                  queryHistory.slice(0, 5).map((q) => (
                    <button
                      key={q.id}
                      onClick={() => handleFollowUp(q.question)}
                      className="w-full text-left p-3 rounded-xl bg-dark-800/50 hover:bg-dark-800 transition-colors border border-dark-700/30 group"
                    >
                      <p className="text-dark-200 text-sm group-hover:text-primary-400 transition-colors truncate">
                        {q.question}
                      </p>
                      <p className="text-dark-600 text-xs mt-1">
                        {new Date(q.created_at).toLocaleDateString()}
                      </p>
                    </button>
                  ))
                )}
              </div>
            </motion.div>

            {/* Quick Tips */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="glass-card p-5 bg-gradient-to-br from-primary-500/5 to-amber-500/2"
            >
              <h3 className="text-sm font-semibold text-dark-200 mb-3 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-emerald-400" />
                Quick Tips
              </h3>
              <ul className="space-y-2 text-dark-400 text-sm">
                <li className="flex items-start gap-2">
                  <span className="text-primary-400 mt-0.5">•</span>
                  Ask questions in natural language
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400 mt-0.5">•</span>
                  Use follow-up questions to drill deeper
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-purple-400 mt-0.5">•</span>
                  Upload CSV or Excel for best results
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-amber-400 mt-0.5">•</span>
                  Charts auto-generate based on data type
                </li>
              </ul>
            </motion.div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
