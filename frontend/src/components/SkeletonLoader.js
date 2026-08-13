import React from 'react';

export const KPISkeleton = () => (
  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse">
    {[...Array(4)].map((_, i) => (
      <div key={i} className="glass-card p-5 space-y-3">
        <div className="flex justify-between items-center">
          <div className="h-3 w-16 bg-dark-700 rounded" />
          <div className="h-8 w-8 bg-dark-700 rounded-lg" />
        </div>
        <div className="h-6 w-24 bg-dark-700 rounded" />
        <div className="h-3 w-12 bg-dark-700 rounded" />
      </div>
    ))}
  </div>
);

export const ChartSkeleton = () => (
  <div className="glass-card p-6 space-y-6 animate-pulse">
    <div className="flex justify-between items-center">
      <div className="space-y-2">
        <div className="h-4 w-36 bg-dark-700 rounded" />
        <div className="h-3 w-48 bg-dark-700 rounded" />
      </div>
      <div className="h-8 w-24 bg-dark-700 rounded-lg" />
    </div>
    <div className="h-[300px] w-full bg-dark-800/50 rounded-xl flex items-end justify-between p-4">
      {[...Array(12)].map((_, i) => {
        const heights = ['h-1/4', 'h-1/2', 'h-3/4', 'h-1/3', 'h-2/3', 'h-5/6'];
        const h = heights[i % heights.length];
        return <div key={i} className={`w-8 ${h} bg-dark-700 rounded-t-md`} />;
      })}
    </div>
  </div>
);

export const SummarySkeleton = () => (
  <div className="glass-card p-6 space-y-4 animate-pulse">
    <div className="h-4 w-28 bg-dark-700 rounded" />
    <div className="space-y-2 pt-2">
      <div className="h-3 w-full bg-dark-700 rounded" />
      <div className="h-3 w-11/12 bg-dark-700 rounded" />
      <div className="h-3 w-4/5 bg-dark-700 rounded" />
    </div>
  </div>
);

export const ProfileSkeleton = () => (
  <div className="glass-card p-5 space-y-4 animate-pulse">
    <div className="h-4 w-32 bg-dark-700 rounded" />
    <div className="space-y-3">
      <div className="flex justify-between">
        <div className="h-3 w-20 bg-dark-700 rounded" />
        <div className="h-3 w-12 bg-dark-700 rounded" />
      </div>
      <div className="flex justify-between">
        <div className="h-3 w-24 bg-dark-700 rounded" />
        <div className="h-3 w-16 bg-dark-700 rounded" />
      </div>
      <div className="flex justify-between">
        <div className="h-3 w-16 bg-dark-700 rounded" />
        <div className="h-3 w-10 bg-dark-700 rounded" />
      </div>
    </div>
  </div>
);

const SkeletonLoader = {
  KPISkeleton,
  ChartSkeleton,
  SummarySkeleton,
  ProfileSkeleton
};

export default SkeletonLoader;
