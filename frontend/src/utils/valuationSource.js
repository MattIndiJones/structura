export const VALUATION_SOURCES = {
  booking: 'Paramètres du booking',
  'booking+overrides': 'Booking avec surcharges',
  realized: 'Volatilités réalisées, dividendes actualisés',
  'realized+overrides': 'Réalisé avec surcharges',
  known_settlement: 'Créance connue à régler',
  unknown: 'Source non renseignée',
}

export function valuationSourceCode(run) {
  if (typeof run === 'string') return Object.hasOwn(VALUATION_SOURCES,run) ? run : 'unknown'
  const source=run?.result?.market_used?.source || run?.result?.mtm?.market_used?.source
    || run?.market_data?.market_used?.source || run?.diagnostics?.effective_source
  // Request intent cannot override the basis actually used by the engine.
  return source ? valuationSourceCode(source) : 'unknown'
}
export const valuationSourceLabel = run => VALUATION_SOURCES[valuationSourceCode(run)]
