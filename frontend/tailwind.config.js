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
          400: '#ff8787',
          500: '#e50914',
          600: '#b81d24',
          700: '#8c141a',
          800: '#6f0d11',
          900: '#4d070b',
        },
        dark: {
          50: '#f9f9f9',
          100: '#f5f5f1',
          200: '#e5e5e5',
          300: '#d2d2d2',
          400: '#808080',
          500: '#555555',
          600: '#333333',
          700: '#222222',
          800: '#181818',
          900: '#141414',
          950: '#000000',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      backdropBlur: {
        xs: '2px',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
        'pulse-glow': 'pulseGlow 2s infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 15px rgba(229, 9, 20, 0.3)' },
          '50%': { boxShadow: '0 0 30px rgba(229, 9, 20, 0.6)' },
        },
      },
    },
  },
  plugins: [],
};
