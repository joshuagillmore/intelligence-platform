import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    // Single glob so shared class tokens (e.g. src/lib/entityStyles.ts, the SSOT
    // for entity colors) are scanned — otherwise JIT never emits classes that
    // live only in src/lib and badges/dots render with no background.
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          900: '#0f1219',
          800: '#1a1f2e',
          700: '#252b3d',
          600: '#313849',
        },
        accent: {
          blue: '#3b82f6',
          cyan: '#06b6d4',
        },
        threat: {
          critical: '#ef4444',
          high: '#f97316',
          medium: '#eab308',
          low: '#6b7280',
        },
      },
      fontFamily: {
        sans: ['Inter', 'SF Pro Display', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
export default config;
