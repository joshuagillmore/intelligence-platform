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
          // The app's most-used accent — headings, active nav, links, panel
          // rules. It lived as a raw #adc6ff in ~174 places before being
          // promoted here; keep it a token so the theme stays changeable.
          periwinkle: '#adc6ff',
        },
        threat: {
          critical: '#ef4444',
          high: '#f97316',
          medium: '#eab308',
          low: '#6b7280',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'Inter', 'SF Pro Display', 'system-ui', 'sans-serif'],
        mono: ['var(--font-jetbrains-mono)', 'JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
export default config;
