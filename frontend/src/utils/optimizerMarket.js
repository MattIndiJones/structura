const clone = value => JSON.parse(JSON.stringify(value))

/** Round editable assumptions in their displayed units, keeping missing values. */
export function roundPricingInput(value) {
  if(value == null || value === '') return value
  return Number(Number(value).toFixed(2))
}

export function marketFields(market) {
  const fields = Object.fromEntries(['rate','yield_curve','funding_spread','funding_curve','correlation'].map(key => [key,market[key]]))
  for (const asset of market.underlyings) for (const field of ['sigma','q','dividend_curve'])
    fields[`underlyings.${asset.ticker}.${field}`] = asset[field]
  return fields
}

/** Explicit copy of the Pricer's GBM inputs, without pricing or fetching data. */
export function optimizerMarketFromPricer(input) {
  if (input.model !== 'constant' || input.rate_model !== 'deterministic')
    throw Error('Choisissez GBM et des taux déterministes dans le Pricer avant de reprendre ses hypothèses.')
  if (!input.underlyings?.length || input.underlyings.length > 3)
    throw Error('L’Optimizer accepte un panier de 1 à 3 sous-jacents.')
  const tickers = input.underlyings.map(u => u.ticker?.trim())
  if (tickers.some(t => !t) || new Set(tickers).size !== tickers.length)
    throw Error('Renseignez des tickers distincts dans le Pricer.')
  if (input.underlyings.some(u => u.ccy !== input.currency || Number(u.ccyh || 0) !== 0
    || Number(u.sigma_fx || 0)*Number(u.rho_sfx || 0) !== 0))
    throw Error('Même devise requise, sans hypothèse FX/quanto ou basis à convertir.')
  const market = {
    source:'PRICER_SESSION', as_of:input.as_of, reference_currency:input.currency, reference_tickers:tickers, captured_at:new Date().toISOString(),
    rate:input.r, yield_curve:clone(input.yield_curve || []),
    funding_spread:input.funding_spread || 0, funding_curve:clone(input.funding_curve || []),
    correlation:clone(input.corr_matrix),
    underlyings:input.underlyings.map(u => ({ticker:u.ticker.trim(),name:u.name,currency:u.ccy,
      asset_type:u.asset_class === 'equity' ? 'equity' : 'index', sigma:u.sigma,q:u.q,
      dividend_curve:clone(u.dividend_curve || [])})),
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(market.as_of || '')) throw Error('Date des hypothèses du Pricer absente.')
  market.provenance = Object.fromEntries(Object.entries(marketFields(market)).map(([key,value]) => [key,{
    source:'PRICER_ASSUMPTION',as_of:market.as_of,reference_value:clone(value),
    method:'Copie explicite des hypothèses GBM de la session Pricer ; donnée de marché non certifiée',
  }]))
  return {currency:input.currency,market:clone(market)}
}

/** Preserve imported references as the user edits values or changes the basket. */
export function withMarketReferences(market, imported) {
  if (!imported) return {...market,source:'USER_ASSUMPTION',provenance:{}}
  return {...market,source:'PRICER_SESSION',captured_at:imported.captured_at,reference_currency:imported.reference_currency,
    reference_tickers:[...imported.reference_tickers],
    provenance:Object.fromEntries(Object.entries(marketFields(market)).map(([key,value]) => [key,
      clone(imported.provenance[key] || {source:'USER_ASSUMPTION',as_of:market.as_of,
        reference_value:value,method:'Hypothèse ajoutée dans l’Optimizer'})]))}
}

export function curveText(curve) {
  return curve?.length ? JSON.stringify(curve.map(([t,rate]) => [t,rate*100])) : ''
}

export function curveRows(curve) {
  return (curve || []).map(([t,rate])=>[t,rate*100])
}

export function parseOptimizerCurve(text) {
  if (Array.isArray(text)) text=JSON.stringify(text)
  if (!String(text || '').trim()) return []
  let curve
  try { curve = JSON.parse(text) } catch { throw Error('La courbe contient une ligne invalide.') }
  if (!Array.isArray(curve) || curve.some(node => !Array.isArray(node) || node.length !== 2
    || node.some(value => typeof value !== 'number' || !Number.isFinite(value))))
    throw Error('Chaque nœud doit contenir une année et un taux numérique en %.')
  return curve.map(([t,rate]) => [t,rate/100])
}

export function remapCorrelations(previousTickers, nextTickers, correlations, fallback=.5) {
  const remapped={}
  for(let i=0;i<nextTickers.length;i++) for(let j=i+1;j<nextTickers.length;j++) {
    const left=nextTickers[i] ? previousTickers.indexOf(nextTickers[i]) : -1
    const right=nextTickers[j] ? previousTickers.indexOf(nextTickers[j]) : -1
    remapped[`${i}-${j}`]=left>=0 && right>=0
      ? correlations[`${Math.min(left,right)}-${Math.max(left,right)}`] ?? fallback : fallback
  }
  return remapped
}

export function emptyOptimizerAsset(ticker = '', kind = '') {
  return {ticker,asset_type:kind,classified:!!kind,vol:null,dividend:null,dividendCurve:[],manual:{vol:false,dividend:false}}
}

export function applyAutomaticAsset(asset, reference) {
  if(!reference || asset.ticker !== reference.ticker) return
  asset.classified=!!reference.asset_type
  if(reference.asset_type) asset.asset_type=reference.asset_type
  if(!asset.manual.vol) asset.vol=reference.sigma == null ? null : roundPricingInput(reference.sigma*100)
  if(!asset.manual.dividend) asset.dividend=reference.q == null ? null : roundPricingInput(reference.q*100)
}

export function withAutomaticReferences(market, reference) {
  const provenance={}
  for(const [key,value] of Object.entries(marketFields(market))) {
    const source=reference?.provenance?.[key]
    provenance[key]=clone(source && source.as_of <= market.as_of ? source : {
      source:'USER_ASSUMPTION',as_of:market.as_of,reference_value:value,method:'Hypothèse explicite dans l’Optimizer',
    })
  }
  return {...market,source:'AUTO_MARKET',captured_at:reference?.captured_at || new Date().toISOString(),
    reference_currency:market.underlyings[0].currency,reference_tickers:market.underlyings.map(u=>u.ticker),provenance}
}
