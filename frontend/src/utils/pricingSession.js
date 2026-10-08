/** Identify an explicit pricing entry independently of module navigation. */
export function pricingEntryKey({ params = {}, query = {} }) {
  if (params.productId) return `product:${params.productId}:${query.calculation || ''}`
  if (params.variantId) return `variant:${params.variantId}`
  if (params.id) return `script:${params.id}`
  if (query.dealId) return `deal:${query.dealId}`
  if (query.fromRfq) return `rfq:${query.fromRfq}`
  if (query.modele) return `model:${query.modele}:${query.sousJacents || ''}:${query.tenor || ''}`
  return null
}

export async function openPricingSession(store, route, load) {
  const key = pricingEntryKey(route)
  if (store.sessionRouteKey && (!key || store.sessionRouteKey === key)) return false
  await load()
  store.sessionRouteKey = key || 'draft'
  return true
}
