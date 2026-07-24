// Remap "inversé" : les rampes slate/blue/red/emerald/green/amber/yellow
// pointent vers les variables CSS du thème clair (voir src/style.css :root).
// Toutes les classes existantes (bg-slate-950, border-red-800, text-emerald-300…)
// se rethèment donc automatiquement, sans toucher au markup des vues.
// Les modificateurs d'opacité (/95, /60, /20…) continuent de fonctionner car
// les variables sont stockées en triplets RGB consommés via <alpha-value>.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`
const ramp = (p) => ({
  50: v(`${p}-50`), 100: v(`${p}-100`), 200: v(`${p}-200`), 300: v(`${p}-300`),
  400: v(`${p}-400`), 500: v(`${p}-500`), 600: v(`${p}-600`), 700: v(`${p}-700`),
  800: v(`${p}-800`), 900: v(`${p}-900`), 950: v(`${p}-950`),
})

export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        slate: ramp('n'),
        blue: ramp('a'),
        brand: ramp('a'),
        red: ramp('neg'),
        emerald: ramp('grn'),
        green: ramp('grn'),
        amber: ramp('gld'),
        yellow: ramp('gld'),

        // Teintes mineures (cartes catégories, chips ponctuels) : remap générique
        // sans variables dédiées — 300/400 = encre foncée, 500-700 inchangés,
        // 800/900/950 = tints clairs. Hex simple : Tailwind gère nativement
        // les modificateurs d'opacité (bg-pink-950/30, etc.).
        pink: {
          300: '#be185d', 400: '#db2777', 500: '#ec4899', 600: '#db2777', 700: '#be185d',
          800: '#fbcfe8', 900: '#fce7f3', 950: '#fdf2f8',
        },
        purple: {
          300: '#7e22ce', 400: '#9333ea', 500: '#a855f7', 600: '#9333ea', 700: '#7e22ce',
          800: '#e9d5ff', 900: '#f3e8ff', 950: '#faf5ff',
        },
        cyan: {
          300: '#0e7490', 400: '#0891b2', 500: '#06b6d4', 600: '#0891b2', 700: '#0e7490',
          800: '#a5f3fc', 900: '#cffafe', 950: '#ecfeff',
        },
        indigo: {
          300: '#4338ca', 400: '#4f46e5', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca',
          800: '#c7d2fe', 900: '#e0e7ff', 950: '#eef2ff',
        },
        orange: {
          300: '#c2410c', 400: '#ea580c', 500: '#f97316', 600: '#ea580c', 700: '#c2410c',
          800: '#fed7aa', 900: '#ffedd5', 950: '#fff7ed',
        },
        sky: {
          300: '#0369a1', 400: '#0284c7', 500: '#0ea5e9', 600: '#0284c7', 700: '#0369a1',
          800: '#bae6fd', 900: '#e0f2fe', 950: '#f0f9ff',
        },
        rose: {
          300: '#be123c', 400: '#e11d48', 500: '#f43f5e', 600: '#e11d48', 700: '#be123c',
          800: '#fecdd3', 900: '#ffe4e6', 950: '#fff1f2',
        },
        violet: {
          300: '#6d28d9', 400: '#7c3aed', 500: '#8b5cf6', 600: '#7c3aed', 700: '#6d28d9',
          800: '#ddd6fe', 900: '#ede9fe', 950: '#f5f3ff',
        },
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif'],
        display: ['Fraunces', 'Georgia', 'serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
