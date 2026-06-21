import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Search, Sparkles, Loader2, ChevronDown } from 'lucide-react';

const QueryInput = ({ datasets, onSubmit, loading }) => {
  const [question, setQuestion] = useState('');
  const [selectedDataset, setSelectedDataset] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!question.trim() || !selectedDataset) return;
    onSubmit({ question: question.trim(), dataset_id: selectedDataset });
  };

  const handleSuggestion = (q) => {
    setQuestion(q);
  };

  const selectedDs = datasets.find((d) => d.id === selectedDataset);

  const suggestions = [
    'What are the top 10 records?',
    'Show me total sales by category',
    'What is the average value?',
    'Show monthly trends',
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="glass-card p-6"
    >
      <h2 className="text-lg font-semibold text-dark-100 mb-4 flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-primary-400" />
        Ask a Question
      </h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Dataset selector */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowDropdown(!showDropdown)}
            className="input-field flex items-center justify-between"
          >
            <span className={selectedDs ? 'text-dark-100' : 'text-dark-500'}>
              {selectedDs ? selectedDs.name : 'Select a dataset...'}
            </span>
            <ChevronDown className={`w-4 h-4 text-dark-400 transition-transform ${showDropdown ? 'rotate-180' : ''}`} />
          </button>
          {showDropdown && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              className="absolute z-10 mt-1 w-full bg-dark-800 border border-dark-600 rounded-xl shadow-2xl overflow-hidden"
            >
              {datasets.length === 0 ? (
                <div className="px-4 py-3 text-dark-500 text-sm">No datasets uploaded yet</div>
              ) : (
                datasets.map((ds) => (
                  <button
                    key={ds.id}
                    type="button"
                    onClick={() => { setSelectedDataset(ds.id); setShowDropdown(false); }}
                    className={`w-full text-left px-4 py-3 min-h-[52px] hover:bg-dark-700 transition-colors ${
                      selectedDataset === ds.id ? 'bg-primary-500/10 text-primary-500' : 'text-dark-200'
                    }`}
                  >
                    <div className="font-medium">{ds.name}</div>
                    <div className="text-xs text-dark-500">
                      {ds.row_count} rows · {ds.column_count} cols · {ds.file_type.toUpperCase()}
                    </div>
                  </button>
                ))
              )}
            </motion.div>
          )}
        </div>

        {/* Query input */}
        <div className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-500" />
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask anything about your data in plain English..."
            className="input-field pl-12 pr-4"
            disabled={loading}
          />
        </div>

        {/* Suggestions */}
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => handleSuggestion(s)}
              className="min-h-[44px] px-4 py-2 text-xs rounded-md bg-dark-800 border border-dark-600 text-dark-400
                         hover:text-primary-500 hover:border-primary-500/50 transition-all"
            >
              {s}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={!question.trim() || !selectedDataset || loading}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Analyzing...
            </>
          ) : (
            <>
              <Sparkles className="w-5 h-5" />
              Generate Insights
            </>
          )}
        </button>
      </form>
    </motion.div>
  );
};

export default QueryInput;
