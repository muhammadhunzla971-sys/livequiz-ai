/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        ink: 'rgb(var(--ink) / <alpha-value>)',
        paper: 'rgb(var(--paper) / <alpha-value>)',
        card: 'rgb(var(--card) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        signal: 'rgb(var(--signal) / <alpha-value>)',
        a1: '#2563eb',
        a2: '#d97706',
        a3: '#0d9488',
        a4: '#c026d3',
        a5: '#475569',
        good: 'rgb(var(--good) / <alpha-value>)',
        bad: 'rgb(var(--bad) / <alpha-value>)',
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', '"Noto Nastaliq Urdu"', 'system-ui', 'sans-serif'],
        body: ['"Atkinson Hyperlegible"', '"Noto Nastaliq Urdu"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
