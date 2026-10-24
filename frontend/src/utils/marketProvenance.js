import { fractionToPercentExact } from './underlyingDefaults.js'

const clone=value=>JSON.parse(JSON.stringify(value))

export function recordMarketReference(row, data, ticker, profile = data.dividend_profiles?.[ticker]) {
  const metadata=clone(row.market_data || {version:1,references:{}})
  metadata.references ||= {};metadata.unavailable ||= {}
  const common=clone({provider:data.provider || 'YAHOO_FINANCE',ticker,unit:'fraction',
    requested_asof:data.requested_asof || null,asof_effective:data.effective_dates?.[ticker] || data.asof_effective || null,
    fetched_at:data.sources?.[ticker]?.fetched_at || data.fetched_at || null,
    source:data.sources?.[ticker],price_type:data.price_type,estimator:data.estimator,
    freshness:data.freshness?.[ticker],warnings:data.warnings || []})
  if(data.vols?.[ticker]!=null) metadata.references.sigma={...common,value:data.vols[ticker],applied_value:Number(row.sigma)/100,
    method:data.estimator?.volatility || 'REALIZED_UNSPECIFIED'}
  const q=profile ? (profile.ok ? profile.yield_declared : null) : data.div_yields?.[ticker]
  if(q!=null && Number.isFinite(q)) {
    metadata.references.q={...common,value:q,applied_value:Number(row.q)/100,
      provider:profile?.provider || common.provider,price_type:profile?.price_type || 'UNVERIFIED_YIELD_FIELD',
      fetched_at:profile?.fetched_at || null,freshness:profile?.freshness?clone(profile.freshness):null,
      asof_effective:profile?.asof_effective || common.asof_effective,
      method:profile?.method || 'UNVERIFIED_YIELD_FIELD',diagnostic:profile?clone(profile):null}
    delete metadata.unavailable.q
  } else metadata.unavailable.q={ticker,asof:data.requested_asof || profile?.asof,
    error:profile?.error || 'Dividende indisponible ; hypothèse conservée.'}
  row.market_data=metadata
}

export function marketProvenanceFields(row) {
  const saved=row?.market_data || row?.market?.market_data
  if(!saved)return {}
  const data=clone(saved),effective={sigma:Number(row.sigma)/100,q:Number(row.q)/100}
  data.version=1;data.effective=effective;data.overrides={}
  for(const field of ['sigma','q']) {
    const ref=data.references?.[field]
    if(ref && (effective[field] !== (ref.applied_value ?? ref.value) || ref.ticker?.toUpperCase() !== row.ticker?.toUpperCase()))
      data.overrides[field]=effective[field]
  }
  return {market_data:data}
}

export function marketProvenanceRows(row) {
  const data=marketProvenanceFields(row).market_data
  if(!data)return []
  return ['sigma','q'].flatMap(field=>{
    const ref=data.references?.[field],missing=data.unavailable?.[field]
    if(!ref && !missing)return []
    return [{field,label:field==='sigma'?'Vol réalisée':'Dividende historique',reference:ref,
      referencePct:ref?fractionToPercentExact(ref.value):null,usedPct:Number(row[field]),
      overridden:field in data.overrides,missing,sourceChanged:!!ref && ref.ticker?.toUpperCase()!==row.ticker?.toUpperCase()}]
  })
}
