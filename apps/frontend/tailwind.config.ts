import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Industrial control-room graphite
        void: '#0B0E13',
        graphite: '#12151C',
        surface: '#181C25',
        raised: '#1F2530',
        line: '#2A313E',
        // The two metals this institute studies
        copper: { DEFAULT: '#C87941', bright: '#E89B5C', deep: '#8A4F28' },
        nickel: { DEFAULT: '#8FA3B0', bright: '#B9CAD4' },
        // Text
        ink: '#E9E6DF',
        muted: '#8B93A1',
        faint: '#5A6270',
        // Semantic encodings (§5.2.3)
        verified: '#3FB68B',
        gap: '#E0A23C',
        contradiction: '#E5484D',
        foreign: '#6C8CD5',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        molten: '0 0 24px -6px rgba(200,121,65,0.45)',
        panel: '0 1px 0 rgba(255,255,255,0.03), 0 12px 40px -12px rgba(0,0,0,0.6)',
      },
      keyframes: {
        pulseThread: {
          '0%,100%': { opacity: '0.35' },
          '50%': { opacity: '0.9' },
        },
        riseIn: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        thread: 'pulseThread 3s ease-in-out infinite',
        rise: 'riseIn 0.4s ease-out both',
      },
    },
  },
  plugins: [],
} satisfies Config;
