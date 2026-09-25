import { defaultUnderlying, fractionToPercent, PERCENT_MARKET_FIELDS } from './underlyingDefaults.js'

function pct(value, fallback) {
  if (value == null || value === '') return fallback
  const number = Number(value)
  return Number.isFinite(number) ? fractionToPercent(number) : fallback
}

export function emptyRfqUnderlying(index = 0, ccy = 'EUR') {
  return { ...defaultUnderlying(index + 1, ccy), market: {} }
}

/** Turn persisted engine units into editable RFQ rows (sigma/q in %). */
export function rfqBasketFromParams(underlyings, fallbackCcy = 'EUR') {
  if (!Array.isArray(underlyings) || !underlyings.length) {
    return [emptyRfqUnderlying(0, fallbackCcy)]
  }
  const rows = underlyings
  return rows.map((source, index) => {
    const { name, ticker, ccy, dividend_curve, dividend_decay, market: nested, ...remaining } = source || {}
    const market = { ...(nested || {}), ...remaining }
    const defaults = defaultUnderlying(index + 1, ccy || fallbackCcy)
    const display = Object.fromEntries(PERCENT_MARKET_FIELDS.map(field =>
      [field, pct(market[field], defaults[field])]))
    const { kappa, ccyh, ...rest } = market
    for (const field of PERCENT_MARKET_FIELDS) delete rest[field]
    return {
      ...defaults,
      ...display,
      kappa: kappa != null && Number.isFinite(Number(kappa)) ? Number(kappa) : defaults.kappa,
      ccyh: ccyh != null && Number.isFinite(Number(ccyh)) ? Math.round(Number(ccyh) * 1e4) : defaults.ccyh,
      name: name || defaults.name,
      ticker: ticker || '',
      ccy: ccy || fallbackCcy,
      market: {
        ...rest,
        ...(dividend_curve?.length ? { dividend_curve } : {}),
        ...(dividend_decay != null ? { dividend_decay } : {}),
      },
    }
  })
}

/** Persist one editable row without losing model-specific per-asset fields. */
export function rfqUnderlyingToParams(row, dividend = {}) {
  const out = {
    ...(row?.market || {}),
    name: row?.name || row?.ticker || 'Sous-jacent',
    ticker: (row?.ticker || '').trim(),
    ccy: row?.ccy || 'EUR',
    kappa: Number(row?.kappa ?? 2),
    ccyh: Number(row?.ccyh ?? 0) / 1e4,
    ...dividend,
  }
  for (const field of PERCENT_MARKET_FIELDS) {
    if (row?.[field] != null) out[field] = Number(row[field]) / 100
  }
  return out
}

export function normaliseCorrelation(matrix, size) {
  const n = Math.max(1, Number(size) || 1)
  return Array.from({ length: n }, (_, i) => Array.from({ length: n }, (__, j) => {
    if (i === j) return 1
    const direct = Number(matrix?.[i]?.[j])
    const symmetric = Number(matrix?.[j]?.[i])
    const value = Number.isFinite(direct) ? direct : (Number.isFinite(symmetric) ? symmetric : 0)
    return Math.max(-1, Math.min(1, value))
  }))
}
