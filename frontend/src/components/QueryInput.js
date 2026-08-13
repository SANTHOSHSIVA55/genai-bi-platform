import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Search, Sparkles, Loader2, ChevronDown, Database, Check, Lightbulb } from 'lucide-react';
import { getDatasetQuestions } from '../api/api';

const QueryInput = ({ datasets, onSubmit, loading, initialQuestion = '', initialDatasetId = null }) => {
  const [question, setQuestion] = useState(initialQuestion);
  const [selectedDatasetIds, setSelectedDatasetIds] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [questions, setQuestions] = useState({ overview: [], category: [], insights: [] });
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const initialQuestionRef = useRef(initialQuestion);

  // Primary dataset is the first of the selection (required by the API).
  const selectedDataset = selectedDatasetIds[0] || '';
  const extraDatasetIds = selectedDatasetIds.slice(1);

  // Auto-select first dataset when datasets load
  useEffect(() => {
    if (datasets.length > 0 && selectedDatasetIds.length === 0) {
      const preferred =
        initialDatasetId && datasets.some((d) => d.id === initialDatasetId)
          ? initialDatasetId
          : datasets[0].id;
      setSelectedDatasetIds([preferred]);
    }
  }, [datasets, selectedDatasetIds, initialDatasetId]);

  // Toggle a dataset in the multi-select; the primary slot always stays filled.
  const toggleDataset = (id) => {
    setSelectedDatasetIds((prev) => {
      if (prev.includes(id)) {
        const next = prev.filter((x) => x !== id);
        return next.length === 0 && datasets.length > 0 ? [datasets[0].id] : next;
      }
      return prev.length === 0 ? [id] : [...prev, id];
    });
  };

  // Apply a question passed in after mount (e.g. re-running from History)
  useEffect(() => {
    if (initialQuestion && initialQuestion !== initialQuestionRef.current) {
      initialQuestionRef.current = initialQuestion;
      setQuestion(initialQuestion);
    }
  }, [initialQuestion]);

  // Schema-aware quick questions for the selected dataset
  const questionsRequestRef = useRef(0);
  const loadQuestions = useCallback(async (datasetId) => {
    if (!datasetId) return;
    // Rapidly switching datasets can resolve out of order; ignore stale
    // responses so suggestions never belong to the wrong dataset.
    const requestId = ++questionsRequestRef.current;
    setQuestionsLoading(true);
    try {
      const res = await getDatasetQuestions(datasetId);
      if (requestId !== questionsRequestRef.current) return;
      const q = res.data || {};
      setQuestions({
        overview: q.overview || [],
        category: q.category || [],
        insights: q.insights || [],
      });
    } catch (err) {
      if (requestId !== questionsRequestRef.current) return;
      setQuestions({ overview: [], category: [], insights: [] });
    } finally {
      if (requestId === questionsRequestRef.current) setQuestionsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQuestions(selectedDataset);
  }, [selectedDataset, loadQuestions]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!question.trim() || !selectedDataset) return;
    onSubmit({
      question: question.trim(),
      dataset_id: selectedDataset,
      ...(extraDatasetIds.length > 0 ? { dataset_ids: extraDatasetIds } : {}),
    });
  };

  const handleSuggestion = (q) => {
    setQuestion(q);
    if (selectedDataset) {
      onSubmit({
        question: q,
        dataset_id: selectedDataset,
        ...(extraDatasetIds.length > 0 ? { dataset_ids: extraDatasetIds } : {}),
      });
    }
  };

  const selectedDs = datasets.find((d) => d.id === selectedDataset);
  const selectedCount = selectedDatasetIds.length;

  const suggestionGroups = [
    questions.overview.length ? { label: 'Overview', items: questions.overview } : null,
    questions.category.length ? { label: 'Compare & Categorize', items: questions.category } : null,
    questions.insights.length ? { label: 'Deep Dive', items: questions.insights } : null,
  ].filter(Boolean);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.08 }}
      className="glass-card p-6"
    >
      <h2 className="text-base font-semibold text-dark-100 mb-4 flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-primary-400" />
        Ask a Question
      </h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowDropdown(!showDropdown)}
            className="input-field flex items-center justify-between"
          >
            <span className={`flex items-center gap-2 ${selectedCount > 0 ? 'text-dark-100' : 'text-dark-500'}`}>
              <Database className="w-4 h-4" />
              {selectedCount === 0
                ? 'Select a dataset...'
                : selectedCount === 1
                  ? selectedDs?.name
                  : `${selectedCount} datasets selected`}
            </span>
            <ChevronDown className={`w-3.5 h-3.5 text-dark-400 transition-transform ${showDropdown ? 'rotate-180' : ''}`} />
          </button>
          {showDropdown && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="absolute z-10 mt-1.5 w-full bg-dark-800/95 border border-white/[0.08] rounded-apple-lg shadow-apple backdrop-blur-2xl overflow-hidden"
            >
              {datasets.length === 0 ? (
                <div className="px-4 py-3 text-dark-500 text-sm">No datasets uploaded yet</div>
              ) : (
                <>
                  <div className="px-4 py-2.5 border-b border-white/[0.06]">
                    <p className="text-[11px] uppercase tracking-wider text-dark-500">
                      Select one or more datasets to combine
                    </p>
                    <p className="text-[11px] text-dark-600 mt-0.5">
                      The first dataset is the primary one; extra datasets are joined when the data supports it.
                    </p>
                  </div>
                  {datasets.map((ds) => {
                    const isSelected = selectedDatasetIds.includes(ds.id);
                    return (
                      <button
                        key={ds.id}
                        type="button"
                        onClick={() => toggleDataset(ds.id)}
                        className={`w-full text-left px-4 py-3 min-h-[48px] hover:bg-white/[0.03] transition-colors flex items-start gap-3 ${
                          isSelected ? 'bg-primary-500/8' : ''
                        }`}
                      >
                        <span className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors ${
                          isSelected
                            ? 'bg-primary-500 border-primary-500 text-white'
                            : 'border-white/[0.15] text-transparent'
                        }`}>
                          <Check className="w-3 h-3" strokeWidth={3} />
                        </span>
                        <span className={isSelected ? 'text-primary-400' : 'text-dark-200'}>
                          <span className="font-medium text-sm block">{ds.name}</span>
                          <span className="text-xs text-dark-500">
                            {ds.row_count} rows &middot; {ds.column_count} cols &middot; {ds.file_type.toUpperCase()}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </>
              )}
            </motion.div>
          )}
        </div>

        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-500" />
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask anything about your data in plain English..."
            className="input-field pl-10 pr-4"
            disabled={loading}
          />
        </div>

        {suggestionGroups.length > 0 && (
          <div className="space-y-2.5">
            <p className="text-[11px] uppercase tracking-wider text-dark-500 flex items-center gap-1.5">
              <Lightbulb className="w-3 h-3" />
              Try a question about this dataset
            </p>
            {suggestionGroups.map((group) => (
              <div key={group.label} className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] text-dark-500 font-medium w-36 flex-shrink-0">{group.label}</span>
                {group.items.slice(0, 3).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => handleSuggestion(s)}
                    disabled={loading}
                    className="min-h-[34px] px-3 py-1.5 text-xs rounded-apple bg-dark-800/60 border border-white/[0.06] text-dark-400
                               hover:text-primary-400 hover:border-primary-500/30 transition-all text-left"
                  >
                    {s}
                  </button>
                ))}
              </div>
            ))}
            {questionsLoading && (
              <div className="flex items-center gap-2 text-xs text-dark-500">
                <Loader2 className="w-3 h-3 animate-spin" />
                Loading schema-aware suggestions...
              </div>
            )}
          </div>
        )}

        <button
          type="submit"
          disabled={!question.trim() || !selectedDataset || loading}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Analyzing...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              Generate Insights
            </>
          )}
        </button>
      </form>
    </motion.div>
  );
};

export default QueryInput;
