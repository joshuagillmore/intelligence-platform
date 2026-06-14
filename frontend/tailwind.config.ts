import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink: 'var(--ink)',
        'ink-soft': 'var(--ink-soft)',
        'ink-muted': 'var(--ink-muted)',
        paper: 'var(--paper)',
        'paper-2': 'var(--paper-2)',
        'paper-3': 'var(--paper-3)',
        line: 'var(--line)',
        'line-soft': 'var(--line-soft)',
        fg: 'var(--fg)',
        'fg-2': 'var(--fg-2)',
        'fg-3': 'var(--fg-3)',
        'fg-4': 'var(--fg-4)',
        signal: 'var(--signal)',
        'signal-ink': 'var(--signal-ink)',
        'signal-soft': 'var(--signal-soft)',
        live: 'var(--live)',
        warn: 'var(--warn)',
        cite: 'var(--cite)',
        violet: 'var(--violet)',
      },
      fontFamily: {
        sans: ['var(--sans)'],
        serif: ['var(--serif)'],
        mono: ['var(--mono)'],
      },
      animation: {
        'pulse-dot': 'pulse-dot 1.6s ease-in-out infinite',
        'slide-up': 'slide-up 0.18s ease',
        'fade-in': 'fade-in 0.15s ease',
        'shimmer': 'shimmer 1.4s linear infinite',
        'scan': 'scan 2s ease infinite',
        'slide-in': 'slide-in 0.18s ease',
        'caret-blink': 'caret-blink 1s step-end infinite',
      },
    },
  },
  plugins: [],
};
export default config;
