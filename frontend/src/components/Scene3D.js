import React from 'react';

/* ───── Ambient Blob ───── */
// Soft gradient blob rendered with a radial gradient instead of a CSS
// `blur()` filter. A large blurred layer is a real GPU/CPU cost on low-end
// machines (it forces a separate composited texture and re-blurs on resize),
// so the "blurred" look is baked into the gradient itself.
const AmbientBlob = ({ color = 'rgba(255, 59, 48, 0.4)', className = '' }) => (
  <div
    className={`absolute rounded-full opacity-20 ${className}`}
    style={{ background: `radial-gradient(circle at center, ${color} 0%, transparent 70%)` }}
  />
);

// Pause every CSS animation on the page when the tab is hidden or the user
// prefers reduced motion. `.motion-paused *` in index.css applies
// `animation-play-state: paused` to each animated descendant.
const usePauseWhenHidden = () => {
  const [paused, setPaused] = React.useState(false);
  React.useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setPaused(mq.matches || document.hidden);
    update();
    mq.addEventListener?.('change', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      mq.removeEventListener?.('change', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, []);
  return paused;
};

/* ───── Rotating SVG Ring ───── */
const SVGRing = ({ size = 200, color = '#ff3b30', duration = 20, reverse = false }) => (
  <div
    className="absolute inset-0 flex items-center justify-center pointer-events-none"
    style={{
      animation: `spin ${duration}s linear infinite ${reverse ? 'reverse' : ''}`,
    }}
  >
    <svg width={size} height={size} viewBox="0 0 100 100" className="opacity-40">
      <circle
        cx="50"
        cy="50"
        r="45"
        fill="none"
        stroke={color}
        strokeWidth="0.5"
        strokeDasharray="4 8"
      />
    </svg>
  </div>
);

/* ───── Neural SVG Network ───── */
const SVGNetwork = () => (
  <svg className="absolute inset-0 w-full h-full opacity-[0.15]" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="netLine" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#ff3b30" stopOpacity="0.8" />
        <stop offset="100%" stopColor="#ff9500" stopOpacity="0.1" />
      </linearGradient>
    </defs>
    <g className="animate-[pulse_8s_infinite]">
      <circle cx="20%" cy="30%" r="3" fill="#ff3b30" />
      <circle cx="35%" cy="20%" r="4" fill="#ff9500" />
      <circle cx="50%" cy="40%" r="3" fill="#ff2d55" />
      <circle cx="65%" cy="25%" r="5" fill="#ff3b30" />
      <circle cx="40%" cy="60%" r="3" fill="#ff2d55" />
      <circle cx="60%" cy="70%" r="4" fill="#ff9500" />
      <circle cx="75%" cy="50%" r="3" fill="#ff3b30" />

      <line x1="20%" y1="30%" x2="35%" y2="20%" stroke="url(#netLine)" strokeWidth="1" />
      <line x1="35%" y1="20%" x2="50%" y2="40%" stroke="url(#netLine)" strokeWidth="1" />
      <line x1="50%" y1="40%" x2="65%" y2="25%" stroke="url(#netLine)" strokeWidth="1" />
      <line x1="50%" y1="40%" x2="40%" y2="60%" stroke="url(#netLine)" strokeWidth="1" />
      <line x1="40%" y1="60%" x2="60%" y2="70%" stroke="url(#netLine)" strokeWidth="1" />
      <line x1="60%" y1="70%" x2="75%" y2="50%" stroke="url(#netLine)" strokeWidth="1" />
    </g>
  </svg>
);

/* ═══════ SCENE PRESETS ═══════ */

// Landing Page — big hero scene
export const HeroScene = () => {
  const paused = usePauseWhenHidden();
  return (
    <div className={`absolute inset-0 bg-dark-950 overflow-hidden select-none pointer-events-none ${paused ? 'motion-paused' : ''}`}>
      {/* Static glow blobs (pre-blurred radial gradients, no CSS blur) */}
      <AmbientBlob color="rgba(224, 32, 32, 0.5)" className="w-[600px] h-[600px] -top-[10%] -left-[10%]" />
      <AmbientBlob color="rgba(220, 38, 38, 0.5)" className="w-[500px] h-[500px] top-[30%] -right-[10%]" />
      <AmbientBlob color="rgba(163, 20, 20, 0.5)" className="w-[700px] h-[700px] -bottom-[20%] left-[20%]" />

      {/* Elegant interactive circles */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="relative w-[300px] h-[300px]">
          <SVGRing size={300} color="#ff3b30" duration={30} />
          <SVGRing size={360} color="#ff9500" duration={45} reverse />
          <SVGRing size={420} color="#ff2d55" duration={60} />
          {/* Glowing center sphere — opacity-only pulse, no per-frame blur */}
          <div className="absolute inset-0 m-auto w-32 h-32 rounded-full bg-gradient-to-br from-primary-500 to-red-600 opacity-60 animate-[pulse_4s_infinite]" />
        </div>
      </div>

      {/* SVG background grid */}
      <div className="absolute inset-0 opacity-[0.03] bg-[linear-gradient(to_right,#808080_1px,transparent_1px),linear-gradient(to_bottom,#808080_1px,transparent_1px)] bg-[size:24px_24px]" />
      <SVGNetwork />
    </div>
  );
};

// Dashboard — subtle background scene
export const DashboardScene = () => (
  <div className="absolute inset-0 bg-dark-950 overflow-hidden select-none pointer-events-none">
    <AmbientBlob color="rgba(224, 32, 32, 0.4)" className="w-[500px] h-[500px] top-[10%] left-[10%]" />
    <AmbientBlob color="rgba(220, 38, 38, 0.4)" className="w-[400px] h-[400px] bottom-[10%] right-[10%]" />
    <div className="absolute inset-0 opacity-[0.015] bg-[linear-gradient(to_right,#808080_1px,transparent_1px),linear-gradient(to_bottom,#808080_1px,transparent_1px)] bg-[size:32px_32px]" />
  </div>
);

// Auth pages — elegant scene
export const AuthScene = () => (
  <div className="absolute inset-0 bg-dark-950 overflow-hidden select-none pointer-events-none">
    <AmbientBlob color="rgba(224, 32, 32, 0.5)" className="w-[400px] h-[400px] -top-[10%] -left-[10%]" />
    <AmbientBlob color="rgba(220, 38, 38, 0.5)" className="w-[400px] h-[400px] -bottom-[10%] -right-[10%]" />
  </div>
);

// Mini 3D widget for cards
export const MiniDataViz = ({ type = 'sphere' }) => {
  return (
    <div className="w-full h-full flex items-center justify-center bg-dark-900/30 rounded-xl overflow-hidden relative border border-white/[0.02]">
      {type === 'sphere' && (
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 rounded-full bg-gradient-to-br from-primary-500 to-red-600 opacity-70 animate-pulse blur-[2px]" />
          <div className="absolute inset-2 rounded-full border border-white/20 animate-spin" style={{ animationDuration: '3s' }} />
        </div>
      )}
      {type === 'brain' && (
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ff2d55" strokeWidth="1.5" className="animate-pulse">
          <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" />
          <path d="M12 6v12" />
          <path d="M8 10h8" />
          <path d="M8 14h8" />
        </svg>
      )}
      {type === 'wire' && (
        <div className="relative w-14 h-14 border border-primary-500/30 rounded-xl animate-[spin_6s_linear_infinite] flex items-center justify-center">
          <div className="w-8 h-8 border border-red-500/30 rounded-lg animate-[spin_3s_linear_infinite_reverse]" />
        </div>
      )}
      {type === 'ring' && (
        <div className="relative w-16 h-16 flex items-center justify-center">
          <div className="absolute w-12 h-12 rounded-full border border-dashed border-primary-500/40 animate-spin" style={{ animationDuration: '4s' }} />
          <div className="absolute w-8 h-8 rounded-full border border-dashed border-red-500/40 animate-spin" style={{ animationDuration: '6s', animationDirection: 'reverse' }} />
        </div>
      )}
    </div>
  );
};

export default HeroScene;
