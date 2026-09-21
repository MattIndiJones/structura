// Scanned inputs take precedence over defaults from a previous study.
export function configurationFromManifest(manifest, benchmarks = [], isinMap = {}) {
  const p = manifest?.params || {}
  const declared = p.benchmark_ticker
  const ticker = declared && declared !== '<À COMPLÉTER>'
    ? declared : (isinMap[manifest?.product?.isin] || 'ACWI')
  const custom = !benchmarks.some(b => b.ticker === ticker)
  return {
    config: {
      ff_series: p.ff_series || 'Developed_5F',
      selected_factors: p.selected_factors || (p.factor_model === 'FF3'
        ? ['Mkt-RF', 'SMB', 'HML']
        : ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', ...(p.factor_model === 'FF5+MOM' ? ['MOM'] : [])]),
      rolling_window: p.rolling_window ?? 60,
      benchmark_ticker: custom ? 'CUSTOM' : ticker,
    },
    customTicker: custom ? ticker : '',
  }
}
