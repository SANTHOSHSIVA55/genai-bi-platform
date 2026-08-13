import React, { Component } from 'react';
import { AlertTriangle, RotateCcw, RefreshCw } from 'lucide-react';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught an error:', error, info);
    if (typeof this.props.onError === 'function') {
      this.props.onError(error, info);
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      const isDev = process.env.NODE_ENV !== 'production';
      return (
        <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center px-4">
          <div className="w-14 h-14 rounded-apple bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <AlertTriangle className="w-7 h-7 text-red-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white mb-1">Something went wrong</h2>
            <p className="text-dark-400 text-sm max-w-md">
              An unexpected error occurred. Try again, or refresh the page.
            </p>
            {isDev && this.state.error && (
              <p className="mt-3 text-xs text-red-400 font-mono bg-dark-800/60 border border-white/[0.06] rounded-lg p-3 overflow-x-auto max-w-lg">
                {String(this.state.error.message || this.state.error)}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button onClick={this.handleRetry} className="btn-secondary text-sm flex items-center gap-2">
              <RotateCcw className="w-4 h-4" />
              Try Again
            </button>
            <button onClick={() => window.location.reload()} className="btn-secondary text-sm flex items-center gap-2">
              <RefreshCw className="w-4 h-4" />
              Refresh Page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
