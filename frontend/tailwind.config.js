/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#fff5f5',
          100: '#ffe3e3',
          200: '#ffc9c9',
          300: '#ffa8a8',
          400: '#ff6b6b',
          500: '#ff3b30',
          600: '#e02020',
          700: '#c41a1a',
          800: '#a31414',
          900: '#7a0e0e',
          950: '#4a0808',
        },
        dark: {
          50: '#f5f5f7',
          100: '#e8e8ed',
          200: '#d1d1d6',
          300: '#aeaeb2',
          400: '#8e8e93',
          500: '#636366',
          600: '#48484a',
          700: '#363639',
          800: '#2c2c2e',
          850: '#222223',
          900: '#1c1c1e',
          950: '#0a0a0b',
        },
        apple: {
          red: '#ff3b30',
          orange: '#ff9500',
          yellow: '#ffcc00',
          green: '#34c759',
          blue: '#007aff',
          teal: '#5ac8fa',
          purple: '#af52de',
          pink: '#ff2d55',
          gray: '#8e8e93',
          separator: '#38383a',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'SF Pro Display', 'system-ui', 'sans-serif'],
      },
      backdropBlur: {
        xs: '2px',
        '4xl': '80px',
      },
      borderRadius: {
        'apple': '10px',
        'apple-lg': '14px',
        'apple-xl': '20px',
      },
      boxShadow: {
        'apple': '0 0 0 0.5px rgba(255, 255, 255, 0.06), 0 8px 40px 0 rgba(0, 0, 0, 0.4)',
        'apple-sm': '0 0 0 0.5px rgba(255, 255, 255, 0.06), 0 4px 12px 0 rgba(0, 0, 0, 0.3)',
        'apple-lg': '0 0 0 0.5px rgba(255, 255, 255, 0.08), 0 16px 60px 0 rgba(0, 0, 0, 0.5)',
        'apple-glow': '0 0 0 1px rgba(255, 59, 48, 0.2), 0 0 20px rgba(255, 59, 48, 0.15)',
        'apple-inner': 'inset 0 1px 0 0 rgba(255, 255, 255, 0.05)',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'pulse-glow': 'pulseGlow 3s ease-in-out infinite',
        'apple-transition': 'appleTransition 0.3s cubic-bezier(0.25, 0.1, 0.25, 1)',
        'scale-in': 'scaleIn 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 10px rgba(255, 59, 48, 0.2)' },
          '50%': { boxShadow: '0 0 25px rgba(255, 59, 48, 0.4)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
};
