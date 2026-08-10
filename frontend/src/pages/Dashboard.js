import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles, Database, Clock, RefreshCw,
  AlertCircle, BarChart3, Loader2, Eye,
  ChevronDown, ChevronUp, Code, Brain,
  Download, FileJson, Table2
} from 'lucide-react';
import { getDatasets, getQueryHistory, executeQuery, getDatasetProfile } from '../api/api';
import { DashboardScene } from '../components/Scene3D';
import KPICards from '../components/KPICards';
import QueryInput from '../components/QueryInput';
import ChartDisplay from '../components/ChartDisplay';
import SummaryPanel from '../components/SummaryPanel';
import AIQualityBadge from '../components/AIQualityBadge';
import PipelineStages from '../components/PipelineStages';
import DatasetProfile from '../components/DatasetProfile';
import GuidancePanel from '../components/GuidancePanel';
import ErrorPanel from '../components/ErrorPanel';
import DatasetPreviewModal from '../components/DatasetPreviewModal';
import { exportCsv, downloadJson } from '../utils/export';
import toast from 'react-hot-toast';

const SQLExplanation = ({ sql }) => {
  const [expanded, setExpanded] = useState(false);
  const explainSQL = (sqlStr) => {
    const upper = sqlStr.toUpperCase();
    const steps = [];
    if (upper.includes('SELECT')) steps.push('Selecting data from the table');
    if (upper.includes('COUNT(')) steps.push('Counting total records');
    if (upper.includes('AVG(')) steps.push('Calculating average values');
    if (upper.includes('SUM(')) steps.push('Calculating total sums');
    if (upper.includes('MIN(')) steps.push('Finding minimum values');
    if (upper.includes('MAX(')) steps.push('Finding maximum values');
    if (upper.includes('DISTINCT')) steps.push('Counting unique values only');
    if (upper.includes('GROUP BY')) {
      const match = sqlStr.match(/GROUP BY\s+"?(\w+)"?/i);
      steps.push(`Grouping results by ${match ? match[1] : 'a category'}`);
    }
    if (upper.includes('ORDER BY')) {
      const dir = upper.includes('DESC') ? 'descending' : 'ascending';
      const match = sqlStr.match(/ORDER BY\s+"?(\w+)"?/i);
      steps.push(`Sorting by ${match ? match[1] : 'a column'} (${dir})`);
    }
    if (upper.includes('LIMIT')) {
      const match = sqlStr.match(/LIMIT\s+(\d+)/i);
      if (match) steps.push(`Showing top ${match[1]} results`);
    }
    return steps.length > 0 ? steps : ['Executing query on your dataset'];
  };

  const explanation = explainSQL(sql);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="glass-card overflow-hidden"
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <Code className="w-4 h-4 text-primary-400" />
          <span className="text-sm font-medium text-dark-200">SQL Query</span>
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-dark-700/50 text-dark-400">
            {explanation.length > 1 ? `${explanation.length} steps` : '1 step'}
          </span>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-dark-400" /> : <ChevronDown className="w-4 h-4 text-dark-400" />}
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/[0.04] pt-3">
          <pre className="text-xs text-dark-300 bg-dark-800/50 rounded-lg p-3 overflow-x-auto font-mono leading-relaxed">{sql}</pre>
          <div className="space-y-1.5">
            {explanation.map((step, i) => (
              <div key={i} className="flex items-center gap-2.5 text-sm text-dark-400">
                <div className="w-5 h-5 rounded-full bg-primary-500/10 flex items-center justify-center flex-shrink-0">
                  <span className="text-[10px] font-bold text-primary-400">{i + 1}</span>
                </div>
                <span>{step}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
};

const detectIntentType = (question) => {
  const q = (question || '').toLowerCase();
  if (/analyze|analysis|summary|overview|describe|tell me about/.test(q)) return 'analysis';
  if (/compare|comparison|across/.test(q)) return 'comparison';
  if (/top\s+\d|bottom\s+\d|rank(?:ed)?|best|worst|highest|lowest/.test(q)) return 'ranking';
  if (/trend|over time|monthly|weekly|daily/.test(q)) return 'time_series';
  if (/how many|total|number of|count/.test(q)) return 'count';
  if (/correlation|relationship|vs|versus/.test(q)) return 'correlation';
  if (/average|avg|sum|total|maximum|minimum/.test(q)) return 'aggregation';
  return 'list';
};

const Dashboard = () => {
  const location = useLocation();
  const [datasets, setDatasets] = useState([]);
  const [queryHistory, setQueryHistory] = useState([]);
  const [queryResult, setQueryResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState(null);
  const [previewTarget, setPreviewTarget] = useState(null);
  const [prefill, setPrefill] = useState(null);
  const [activeDatasetId, setActiveDatasetId] = useState(null);
  const [profile, setProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const lastDatasetId = useRef(null);

  useEffect(() => {
    const state = location.state;
    if (state?.question) {
      setPrefill({ question: state.question, datasetId: state.datasetId || null });
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  const fetchData = useCallback(async () => {
    try {
      const [dsRes, histRes] = await Promise.all([
        getDatasets(),
        getQueryHistory(),
      ]);
      const ds = Array.isArray(dsRes.data) ? dsRes.data : (dsRes.data?.datasets || []);
      const hist = Array.isArray(histRes.data) ? histRes.data : (histRes.data?.queries || []);
      setDatasets(ds);
      setQueryHistory(hist);
      setError(null);
      if (ds.length > 0 && !lastDatasetId.current) {
        lastDatasetId.current = ds[0].id;
        setActiveDatasetId(ds[0].id);
      }
    } catch (err) {
      console.warn('Could not fetch initial data:', err);
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Unable to connect to the server.');
      setDatasets([]);
      setQueryHistory([]);
    } finally {
      setInitialLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-insights profile for the active dataset
  useEffect(() => {
    if (!activeDatasetId) {
      setProfile(null);
      return;
    }
    let cancelled = false;
    setProfileLoading(true);
    getDatasetProfile(activeDatasetId)
      .then((res) => { if (!cancelled) setProfile(res.data); })
      .catch(() => { if (!cancelled) setProfile(null); })
      .finally(() => { if (!cancelled) setProfileLoading(false); });
    return () => { cancelled = true; };
  }, [activeDatasetId]);

  const handleQuery = async (queryData) => {
    setLoading(true);
    setQueryResult(null);
    setError(null);
    lastDatasetId.current = queryData.dataset_id || lastDatasetId.current;
    if (queryData.dataset_id) setActiveDatasetId(queryData.dataset_id);
    try {
      const res = await executeQuery(queryData);
      setQueryResult(res.data);
      toast.success('Query executed successfully!');
      const histRes = await getQueryHistory().catch(() => null);
      if (histRes) {
        setQueryHistory(Array.isArray(histRes.data) ? histRes.data : (histRes.data?.queries || []));
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail && typeof detail === 'object' && detail?.error) {
        setQueryResult({
          question: detail.question || queryData.question,
          generated_sql: detail.generated_sql || '',
          data: [],
          chart_type: 'table',
          chart_config: { chart_type: 'table', x_axis: '', y_axis: '', title: 'Query Error' },
          summary: {
            executive_summary: [],
            recommendations: [],
            risks: [],
            follow_up_questions: [],
          },
          ai_quality: null,
          validation_info: {
            valid: false,
            issues: [detail.error],
            suggested_fix: detail.suggested_fix || null,
          },
        });
        toast.error(detail.error);
      } else {
        const msg = typeof detail === 'string' ? detail : 'Unable to connect to the server. Please ensure the backend is running.';
        setError(msg);
        toast.error(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleFollowUp = (question, datasetId) => {
    const id = datasetId || lastDatasetId.current || (datasets.length > 0 ? datasets[0].id : null);
    if (id) {
      handleQuery({ question, dataset_id: id });
    }
  };

  const handleExportCsv = () => {
    if (queryResult?.data?.length) {
      exportCsv(queryResult.data, `${queryResult.question.slice(0, 40).replace(/[^\w\s-]/g, '').trim() || 'query'}-results.csv`);
    }
  };

  const handleExportJson = () => {
    if (queryResult?.data?.length) {
      downloadJson(queryResult.data, 'query-results.json');
    }
  };

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
          <p className="text-dark-400 text-sm">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative">
      <div className="fixed inset-0 z-0 opacity-20 pointer-events-none">
        <DashboardScene />
      </div>

      <div className="relative z-10 space-y-6">
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"
        >
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-3">
              <Sparkles className="w-6 h-6 text-primary-400" />
              Dashboard
            </h1>
            <p className="text-dark-400 text-sm mt-0.5">Your data intelligence hub</p>
          </div>
          <button
            onClick={fetchData}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </motion.div>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="flex items-center gap-3 p-4 rounded-apple-lg bg-amber-500/8 border border-amber-500/15 text-amber-300"
            >
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <p className="text-sm">{error}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {!error && datasets.length === 0 && !loading && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card p-8 text-center"
          >
            <div className="w-14 h-14 rounded-2xl bg-dark-800/60 flex items-center justify-center mx-auto mb-4 border border-white/[0.04]">
              <Database className="w-7 h-7 text-dark-500" />
            </div>
            <h3 className="text-dark-100 font-semibold mb-1">No datasets yet</h3>
            <p className="text-dark-400 text-sm mb-5">
              Upload your first dataset to start asking questions in plain English.
            </p>
            <Link to="/upload" className="btn-primary inline-flex items-center gap-2 text-sm">
              <Table2 className="w-4 h-4" />
              Upload a Dataset
            </Link>
          </motion.div>
        )}

        <KPICards datasets={datasets} queryCount={queryHistory.length} />

        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <QueryInput
              datasets={datasets}
              onSubmit={handleQuery}
              loading={loading}
              initialQuestion={prefill?.question || ''}
              initialDatasetId={prefill?.datasetId}
            />

            <AnimatePresence>
              {loading && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="glass-card p-8 flex flex-col items-center gap-5"
                >
                  <div className="relative">
                    <div className="w-14 h-14 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
                    <Sparkles className="w-5 h-5 text-primary-400 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                  </div>
                  <div className="text-center space-y-2">
                    <p className="text-dark-200 font-medium">AI is analyzing your data...</p>
                    <div className="flex flex-wrap items-center justify-center gap-3 text-[11px]">
                      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-dark-700/50 text-dark-400">
                        <Brain className="w-3 h-3" /> Understanding question
                      </span>
                      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-dark-700/50 text-dark-400">
                        <Database className="w-3 h-3" /> Querying data
                      </span>
                      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-dark-700/50 text-dark-400">
                        <BarChart3 className="w-3 h-3" /> Building chart
                      </span>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {queryResult && (
              <>
                {queryResult.ai_quality && (
                  <AIQualityBadge quality={queryResult.ai_quality} />
                )}

                {queryResult.pipeline_stages && queryResult.pipeline_stages.length > 0 && (
                  <PipelineStages stages={queryResult.pipeline_stages} />
                )}

                {queryResult.chart_config?.title === 'Guidance' ? (
                  <GuidancePanel
                    message={(queryResult.summary?.executive_summary || [])[0] || 'Please ask a more specific question.'}
                    issues={queryResult.validation_info?.issues}
                    generatedSql={queryResult.generated_sql}
                    followUps={queryResult.follow_up_questions}
                    onFollowUp={(q) => handleFollowUp(q)}
                  />
                ) : (
                  <>
                {queryResult.validation_info && !queryResult.validation_info.valid && (
                  <ErrorPanel
                    question={queryResult.question}
                    generatedSql={queryResult.generated_sql}
                    issues={queryResult.validation_info.issues}
                    onRegenerate={() => {
                      if (lastDatasetId.current) {
                        handleQuery({ question: queryResult.question, dataset_id: lastDatasetId.current });
                      }
                    }}
                    suggestedFix={queryResult.validation_info.suggested_fix}
                  />
                )}

                {queryResult.data && queryResult.data.length === 0 && !queryResult.generated_sql && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="glass-card p-8 text-center"
                  >
                    <p className="text-dark-500 text-sm">No data returned for this query. Try rephrasing your question.</p>
                  </motion.div>
                )}

                {queryResult.data && queryResult.data.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex items-center justify-end gap-2"
                  >
                    <button onClick={handleExportCsv} className="btn-secondary text-xs flex items-center gap-1.5">
                      <Download className="w-3.5 h-3.5" />
                      Export CSV
                    </button>
                    <button onClick={handleExportJson} className="btn-secondary text-xs flex items-center gap-1.5">
                      <FileJson className="w-3.5 h-3.5" />
                      JSON
                    </button>
                  </motion.div>
                )}

                <ChartDisplay
                  data={queryResult.data}
                  chartConfig={queryResult.chart_config}
                  intentType={detectIntentType(queryResult.question)}
                  currency={queryResult.currency}
                  semanticTypes={queryResult.semantic_types}
                />

                {queryResult.generated_sql && (
                  <SQLExplanation sql={queryResult.generated_sql} />
                )}

                <SummaryPanel
                  summary={queryResult.summary}
                  generatedSql={queryResult.generated_sql}
                  onFollowUp={(q) => handleFollowUp(q)}
                />
                  </>
                )}
              </>
            )}
          </div>

          <div className="space-y-6">
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
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
                    <div key={ds.id} className="group p-3 rounded-apple bg-dark-800/40 hover:bg-dark-800/60 transition-colors border border-white/[0.04]">
                      <div className="flex items-start justify-between">
                        <div className="min-w-0 flex-1">
                          <button
                            onClick={() => setPreviewTarget(ds)}
                            className="text-left w-full"
                          >
                            <p className="text-dark-100 font-medium text-sm truncate group-hover:text-primary-400 transition-colors">
                              {ds.name}
                            </p>
                            <p className="text-dark-500 text-xs mt-1">
                              {(ds.row_count || 0).toLocaleString()} rows &middot; {ds.column_count || 0} cols
                              <span className="ml-2 px-1.5 py-0.5 rounded bg-dark-700/50 text-dark-400 uppercase text-[10px]">
                                {ds.file_type}
                              </span>
                            </p>
                          </button>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                          <button
                            onClick={() => setPreviewTarget(ds)}
                            className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg bg-dark-700/40 hover:bg-dark-700/70 border border-white/[0.05]"
                            title="Preview data"
                            aria-label={`Preview ${ds.name}`}
                          >
                            <Eye className="w-3.5 h-3.5 text-dark-300" />
                          </button>
                          <button
                            onClick={() => handleQuery({ question: 'Analyze this dataset and give me a complete business summary', dataset_id: ds.id })}
                            className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg bg-primary-500/10 hover:bg-primary-500/20 border border-primary-500/20"
                            title="Run business analysis"
                            aria-label={`Analyze ${ds.name}`}
                          >
                            <Brain className="w-3.5 h-3.5 text-primary-400" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </motion.div>

            {activeDatasetId && (
              <DatasetProfile
                profile={profile}
                loading={profileLoading}
                datasetName={datasets.find((d) => d.id === activeDatasetId)?.name}
              />
            )}

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.25 }}
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
                      onClick={() => handleFollowUp(q.question, q.dataset_id)}
                      className="w-full text-left p-3 rounded-apple bg-dark-800/40 hover:bg-dark-800/60 transition-colors border border-white/[0.04] group"
                    >
                      <p className="text-dark-200 text-sm group-hover:text-primary-400 transition-colors truncate">
                        {q.question}
                      </p>
                      <p className="text-dark-500 text-xs mt-1">
                        {new Date(q.created_at).toLocaleDateString()}
                      </p>
                    </button>
                  ))
                )}
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.35 }}
              className="glass-card p-5"
            >
              <h3 className="text-sm font-semibold text-dark-200 mb-3 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-primary-400" />
                Quick Tips
              </h3>
              <ul className="space-y-2 text-dark-400 text-sm">
                <li className="flex items-start gap-2">
                  <span className="text-primary-400 mt-0.5">&bull;</span>
                  Ask questions in natural language
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-apple-green mt-0.5">&bull;</span>
                  Use follow-up questions to drill deeper
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-apple-blue mt-0.5">&bull;</span>
                  Upload CSV or Excel for best results
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-apple-orange mt-0.5">&bull;</span>
                  Charts auto-generate based on data type
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-primary-400 mt-0.5">&bull;</span>
                  Click <Brain className="w-3 h-3 inline text-primary-400" /> on a dataset for instant analysis
                </li>
              </ul>
            </motion.div>
          </div>
        </div>
      </div>

      <DatasetPreviewModal
        datasetId={previewTarget?.id}
        datasetName={previewTarget?.name}
        open={!!previewTarget}
        onClose={() => setPreviewTarget(null)}
      />
    </div>
  );
};

export default Dashboard;
