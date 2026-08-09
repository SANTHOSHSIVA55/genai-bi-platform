import React from 'react';
import { Sparkles } from 'lucide-react';

const FullPageLoader = () => (
  <div className="min-h-screen bg-dark-950 grid-bg flex items-center justify-center">
    <div className="flex flex-col items-center gap-4">
      <div className="relative">
        <div className="w-12 h-12 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
        <Sparkles className="w-4 h-4 text-primary-400 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
      </div>
      <p className="text-dark-400 text-sm">Loading...</p>
    </div>
  </div>
);

export default FullPageLoader;
