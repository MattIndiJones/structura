// Thème central Chart.js — thème clair "institutional finance". Mute
// Chart.defaults une seule fois par fichier consommateur (applyChartTheme,
// appelé à côté du Chart.register(...) existant de chaque vue/composant à
// charts) : couvre grille/axes/tooltip/légende sans qu'ils aient besoin de
// redéclarer ces couleurs chacun. Mutation idempotente — sans risque à
// être appelée depuis plusieurs fichiers.
//
// Ce module n'importe volontairement PAS 'chart.js' lui-même (le paquet
// pèse ~200 Ko) : applyChartTheme reçoit la classe Chart déjà importée par
// l'appelant, pour ne jamais tirer chart.js dans le chunk d'entrée
// principal si ce module était un jour importé depuis main.js ou un
// fichier hors du périmètre des charts.
export const chartTheme = {
  grid: '#eceae4',
  gridStrong: '#e2ddd6',
  ticks: '#7a7469',
  ink: '#1a1814',
  surface: '#ffffff',
  border: '#ccc8bf',

  primary: '#2563eb',
  primaryFill: 'rgba(37, 99, 235, .45)',
  primarySoft: 'rgba(37, 99, 235, .12)',

  positive: '#1a7a4a',
  positiveFill: 'rgba(26, 122, 74, .35)',
  negative: '#c0392b',
  negativeFill: 'rgba(192, 57, 43, .30)',
  gold: '#b8860b',

  annotation: '#1a1814',
  annotationDanger: '#c0392b',

  // Palette de séries curatée — cohérente avec les tokens sémantiques
  // (bleu accent en premier, puis vert/or/rouge/violet/cyan/rose/orange).
  series: ['#2563eb', '#1a7a4a', '#b8860b', '#c0392b', '#7c5cd6', '#0e7490', '#d2649a', '#5a6b7a'],
}

/**
 * Formate une graduation d'axe avec juste ce qu'il faut de décimales.
 *
 * Le nombre de décimales se déduit du PAS entre graduations, pas de la valeur :
 * un axe qui monte de 0,05 en 0,05 a besoin de deux décimales, un axe qui monte
 * de 1000 en 1000 n'en a besoin d'aucune. Sans ça, `value + '%'` recrache le
 * flottant brut — l'axe du solveur affichait « 46.150000000000006 % ».
 */
export function axisNumber(value, ticks, maxDecimals = 2) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return value
  const values = (Array.isArray(ticks) ? ticks : [])
    .map(tick => Number(tick?.value))
    .filter(Number.isFinite)
  const steps = values
    .slice(1)
    .map((current, index) => Math.abs(current - values[index]))
    .filter(step => step > 0)
  const step = steps.length > 0 ? Math.min(...steps) : 1
  const decimals = step >= 1 ? 0 : step >= 0.1 ? 1 : maxDecimals

  return numericValue.toLocaleString('fr-FR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/**
 * Fabrique un `callback` de graduation avec suffixe — la forme qu'attend
 * Chart.js. `axisTick('%')` remplace `v => v + '%'`, qui était la source du
 * bruit de virgule flottante partout où il apparaissait.
 */
export function axisTick(suffix = '', maxDecimals = 2) {
  return (value, _index, ticks) => `${axisNumber(value, ticks, maxDecimals)}${suffix}`
}

export function applyChartTheme(Chart) {
  Chart.defaults.font.family = "'Plus Jakarta Sans', system-ui, sans-serif"
  Chart.defaults.font.size = 11
  Chart.defaults.color = chartTheme.ticks
  Chart.defaults.borderColor = chartTheme.grid

  Chart.defaults.scale.grid.color = chartTheme.grid
  Chart.defaults.scale.ticks.color = chartTheme.ticks
  Chart.defaults.scale.border.color = chartTheme.border

  Chart.defaults.plugins.legend.labels.color = chartTheme.ticks
  Chart.defaults.plugins.legend.labels.font = { size: 10 }

  Chart.defaults.plugins.tooltip.backgroundColor = chartTheme.surface
  Chart.defaults.plugins.tooltip.borderColor = chartTheme.border
  Chart.defaults.plugins.tooltip.borderWidth = 1
  Chart.defaults.plugins.tooltip.titleColor = chartTheme.ink
  Chart.defaults.plugins.tooltip.bodyColor = chartTheme.ink
  Chart.defaults.plugins.tooltip.padding = 8
  Chart.defaults.plugins.tooltip.cornerRadius = 8
  Chart.defaults.plugins.tooltip.boxPadding = 4
}
