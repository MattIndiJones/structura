// Historical eligibility is independent of today's execution availability.
export function isHistoricalQuoteEligible(quote) {
  if (quote.superseded || quote.edge_bps == null || !Number.isFinite(quote.edge_bps)) return false
  if (typeof quote.history_eligible === 'boolean') return quote.history_eligible
  return quote.origin !== 'NETWORK' || quote.comparable === true
}

export function aggregateDailyQuoteEdges(history, providers) {
  const labels = [...new Set(history.map(row => row.date.slice(0, 10)))].sort()
  const series = providers.map(provider => {
    const buckets = new Map()
    for (const row of history) {
      if (row.provider !== provider) continue
      const day = row.date.slice(0, 10)
      if (!buckets.has(day)) buckets.set(day, [])
      buckets.get(day).push(row.edge_bps)
    }
    return { provider, values: labels.map(day => {
      const values = buckets.get(day)?.sort((a, b) => a - b)
      return values ? values.reduce((sum, value) => sum + value, 0) / values.length : null
    }), counts: labels.map(day => buckets.get(day)?.length || 0) }
  })
  return { labels, series }
}
