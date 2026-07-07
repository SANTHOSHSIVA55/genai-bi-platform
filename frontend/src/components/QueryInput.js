import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Search, Sparkles, Loader2, ChevronDown, Database } from 'lucide-react';

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
    'How many suppliers are there?',
    'Show me total records',
    'List all available data',
    'What is the average value?',
  ];

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
            <span className={`flex items-center gap-2 ${selectedDs ? 'text-dark-100' : 'text-dark-500'}`}>
              <Database className="w-4 h-4" />
              {selectedDs ? selectedDs.name : 'Select a dataset...'}
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
                datasets.map((ds) => (
                  <button
                    key={ds.id}
                    type="button"
                    onClick={() => { setSelectedDataset(ds.id); setShowDropdown(false); }}
                    className={`w-full text-left px-4 py-3 min-h-[48px] hover:bg-white/[0.03] transition-colors ${
                      selectedDataset === ds.id ? 'bg-primary-500/8 text-primary-400' : 'text-dark-200'
                    }`}
                  >
                    <div className="font-medium text-sm">{ds.name}</div>
                    <div className="text-xs text-dark-500">
                      {ds.row_count} rows &middot; {ds.column_count} cols &middot; {ds.file_type.toUpperCase()}
                    </div>
                  </button>
                ))
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

        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => handleSuggestion(s)}
              className="min-h-[36px] px-3 py-1.5 text-xs rounded-apple bg-dark-800/60 border border-white/[0.06] text-dark-400
                         hover:text-primary-400 hover:border-primary-500/30 transition-all"
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
