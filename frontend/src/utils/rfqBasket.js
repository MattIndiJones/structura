function pct(value, fallback) {
  const number = Number(value)
  return Number.isFinite(number) ? number * 100 : fallback
}

export function emptyRfqUnderlying(index = 0, ccy = 'EUR') {
  return {
    name: `Sous-jacent ${index + 1}`,
    ticker: '',
    ccy,
    sigma: 20,
    q: 2,
    market: {},
  }
}

/** Turn persisted engine units into editable RFQ rows (sigma/q in %). */
export function rfqBasketFromParams(underlyings, fallbackCcy = 'EUR') {
  const rows = Array.isArray(underlyings) && underlyings.length
    ? underlyings : [emptyRfqUnderlying(0, fallbackCcy)]
  return rows.map((source, index) => {
    const {
      name, ticker, ccy, sigma, q, dividend_curve, dividend_decay, ...market
    } = source || {}
    return {
      name: name || `Sous-jacent ${index + 1}`,
      ticker: ticker || '',
      ccy: ccy || fallbackCcy,
      sigma: pct(sigma, 20),
      q: pct(q, 2),
      market: {
        ...market,
        ...(dividend_curve?.length ? { dividend_curve } : {}),
        ...(dividend_decay != null ? { dividend_decay } : {}),
      },
    }
  })
}

/** Persist one editable row without losing model-specific per-asset fields. */
export function rfqUnderlyingToParams(row, dividend = {}) {
  return {
    ...(row?.market || {}),
    name: row?.name || row?.ticker || 'Sous-jacent',
    ticker: (row?.ticker || '').trim(),
    ccy: row?.ccy || 'EUR',
    sigma: Number(row?.sigma ?? 20) / 100,
    q: Number(row?.q ?? 0) / 100,
    ...dividend,
  }
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
