import React, { Component } from 'react';
import { AlertTriangle } from 'lucide-react';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught an error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center px-4">
          <div className="w-14 h-14 rounded-apple bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <AlertTriangle className="w-7 h-7 text-red-400" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white mb-1">Something went wrong</h2>
            <p className="text-dark-400 text-sm">
              An unexpected error occurred. Try refreshing the page.
            </p>
          </div>
          <button onClick={() => window.location.reload()} className="btn-secondary text-sm">
            Refresh Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
