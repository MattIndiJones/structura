export const CALCULATION_LIMITS = Object.freeze({
  maxScriptChars: 32_000,
  maxScriptLines: 1_000,
  maxExpandedDates: 5_000,
  maturityWarningYears: 10,
  maxMaturityYears: 30,
  underlyingWarningCount: 6,
  maxUnderlyings: 12,
  syncMemoryBytes: 1024 ** 3,
  syncWorkUnits: 250_000_000,
})

const MODEL_WORK = { constant: 1, heston: 2, sabr: 2, localvol: 2.5, lsv: 3.5 }
const MODEL_ARRAYS = { constant: 2, heston: 3, sabr: 3, localvol: 2.5, lsv: 3.5 }
const SCRIPT_EVENT_WORK = 4

function literalDateCount(script) {
  let count = 0
  for (const line of String(script).split('\n')) {
    const match = line.trim().match(/^AT\s+(.+?):?$/i)
    if (!match) continue
    const header = match[1].replace(/:$/, '').trim()
    if (/^(MATURITY|[A-Za-z_])/i.test(header)) continue
    for (const rawPart of header.split(',')) {
      const part = rawPart.trim().replace(/[Yy]$/, '')
      const range = part.match(/^([+-]?[\d.]+)\.\.([+-]?[\d.]+)(?::([+-]?[\d.]+))?$/)
      if (!range) {
        if (Number.isFinite(Number(part))) count += 1
        continue
      }
      const start = Number(range[1]); const end = Number(range[2])
      const step = range[3] == null ? 1 : Number(range[3])
      if (Number.isFinite(start) && Number.isFinite(end) && step > 0 && end >= start) {
        count += Math.floor((end - start + 1e-9) / step) + 1
      }
      if (count > CALCULATION_LIMITS.maxExpandedDates) return count
    }
  }
  return count
}

function greekRuns(selected, underlyings) {
  const sel = new Set(selected || [])
  let count = 0
  if (['gamma', 'theta', 'corr'].some(g => sel.has(g))) count += 1
  if (sel.has('delta') || sel.has('gamma')) count += 2 * underlyings
  if (sel.has('gamma')) count += 2 * underlyings
  if (sel.has('vega')) count += 2 * underlyings
  if (sel.has('rho')) count += 2
  if (sel.has('credit')) count += 2
  if (sel.has('corr') && underlyings > 1) count += underlyings * (underlyings - 1) / 2
  if (sel.has('theta')) count += 1
  return count
}

function oneRun({ maturityYears, underlyings, paths, model, antithetic,
  continuousMonitoring, stochasticRates, expandedDates = 0, repricings = 1 }) {
  const steps = Math.max(1, Math.round(maturityYears * 52))
  let workFactor = MODEL_WORK[model] ?? 1
  if (antithetic) workFactor *= 2
  if (continuousMonitoring) workFactor *= 1.35
  if (stochasticRates) workFactor *= 1.25
  const simulationUnits = steps * underlyings * paths * workFactor
  const pathLegs = antithetic ? 2 : 1
  const scriptUnits = expandedDates * paths * pathLegs * SCRIPT_EVENT_WORK
  const workUnits = Math.ceil((simulationUnits + scriptUnits) * repricings)

  let arrayFactor = MODEL_ARRAYS[model] ?? 2
  if (continuousMonitoring) arrayFactor += 1
  const cells = (steps + 1) * underlyings * paths
  let peakBytes = Math.ceil(cells * 8 * arrayFactor * 1.35)
  if (stochasticRates) peakBytes += Math.ceil((steps + 1) * paths * 8 * 3 * 1.2)
  return { steps, workUnits, peakBytes }
}

export function estimatePricingCalculation({ script = '', maturityYears, underlyings,
  paths, model, antithetic = true, continuousMonitoring = false,
  stochasticRates = false, selectedGreeks = [] }) {
  const maturity = Number(maturityYears)
  const assets = Number(underlyings)
  const nPaths = Number(paths)
  const lines = String(script).split('\n').length
  const expandedDates = literalDateCount(script)
  const reasons = []
  const warnings = []

  if (!Number.isFinite(maturity) || maturity <= 0) reasons.push('Maturité invalide')
  else if (maturity > CALCULATION_LIMITS.maxMaturityYears) reasons.push('Maturité supérieure à 30 ans')
  else if (maturity > CALCULATION_LIMITS.maturityWarningYears) warnings.push('Maturité longue')
  if (!Number.isInteger(assets) || assets < 1) reasons.push('Panier vide')
  else if (assets > CALCULATION_LIMITS.maxUnderlyings) reasons.push('Plus de 12 sous-jacents')
  else if (assets > CALCULATION_LIMITS.underlyingWarningCount) warnings.push('Panier large')
  if (!Number.isFinite(nPaths) || nPaths < 1) reasons.push('Nombre de trajectoires invalide')
  if (String(script).length > CALCULATION_LIMITS.maxScriptChars) reasons.push('Script supérieur à 32 000 caractères')
  if (lines > CALCULATION_LIMITS.maxScriptLines) reasons.push('Script supérieur à 1 000 lignes')
  if (expandedDates > CALCULATION_LIMITS.maxExpandedDates) reasons.push('Plus de 5 000 dates développées')

  if (reasons.length) {
    return { blocked: true, level: 'blocked', reasons, warnings, workUnits: 0, peakBytes: 0,
      estimatedPeakMb: 0, repricings: 0 }
  }

  const input = { maturityYears: maturity, underlyings: assets, paths: nPaths, model,
    antithetic, continuousMonitoring, stochasticRates, expandedDates }
  const base = oneRun(input)
  const runs = greekRuns(selectedGreeks, assets)
  const greekPaths = Math.max(1_000, Math.floor(nPaths / 4))
  const greek = runs ? oneRun({ ...input, paths: greekPaths, repricings: runs }) : null
  const workUnits = base.workUnits + (greek?.workUnits || 0)
  const peakBytes = Math.max(base.peakBytes, greek?.peakBytes || 0)
  if (workUnits > CALCULATION_LIMITS.syncWorkUnits || peakBytes > CALCULATION_LIMITS.syncMemoryBytes) {
    reasons.push('Calcul trop lourd pour une exécution synchrone')
  }
  return {
    blocked: reasons.length > 0,
    level: reasons.length ? 'blocked' : (warnings.length ? 'warning' : 'normal'),
    reasons,
    warnings,
    workUnits,
    peakBytes,
    estimatedPeakMb: Math.round(peakBytes / 1024 ** 2 * 10) / 10,
    repricings: 1 + runs * greekPaths / nPaths,
    expandedDates,
  }
}
