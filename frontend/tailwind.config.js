/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  corePlugins: {
    // Preserve existing Smart Land Evaluation global styles without Tailwind reset conflicts
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        obsidian: '#111315',
        ivory: '#F4F0E8',
        stone: '#AEB5B8',
        charcoal: {
          950: '#0F1115',
          900: '#161920',
          800: '#1E222B',
          700: '#2A303C',
        },
        gold: {
          600: '#9A722A',
          500: '#C6A15B',
          400: '#D4A853',
          100: '#FBF5E8',
        },
      },
      fontFamily: {
        serif: ['Cinzel', 'Georgia', 'serif'],
        sans: ['Plus Jakarta Sans', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['Space Mono', 'JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};
