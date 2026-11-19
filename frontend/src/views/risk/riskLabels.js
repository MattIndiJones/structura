// Pure labels and formats of the Risk Management screen, moved out of
// RiskManagementView.vue (P1-10, U3). No state here.

export function dealHasPortfolio(deal, portfolioId) {
  return (deal.portfolio_ids || []).includes(portfolioId)
}

export function dealPortfolioLabel(deal) {
  const count = (deal.portfolio_ids || []).length
  return count ? `${count} portefeuille${count > 1 ? 's' : ''}` : 'Non classé'
}

export const VEGA_SCOPE_LABELS = {
  total: 'vol totale',
  leg_independante: 'jambe indépendante',
  effective_local_vol: 'vol locale effective, variance figée',
  non_documente: 'périmètre non documenté',
}

export function vegaScopeLabel(scope) {
  return VEGA_SCOPE_LABELS[scope] || scope || 'périmètre non documenté'
}

export function vegaScopeTotal(bucket, scope) {
  return bucket?.vega_by_scope_eur?.[scope] ?? null
}

export function vegaRows(bucket) {
  return (bucket?.vega_scopes || []).map(scope => ({
    scope,
    value: vegaScopeTotal(bucket, scope),
  }))
}

export function sharePct(contribution, bucketTotal) {
  if (contribution == null || !bucketTotal) return '—'
  return `${Math.round((contribution / bucketTotal) * 100)}%`
}

export function formatElapsed(seconds) {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return mins ? `${mins} min ${String(secs).padStart(2, '0')} s` : `${secs} s`
}
