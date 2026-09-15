export function mtmValue(run) {
  const value = run?.result?.mtm
  return typeof value === 'number' ? value : value?.mtm
}

export function valuationDate(run) {
  return run?.result?.valuation_date
    || run?.diagnostics?.request?.valuation_date
    || run?.result?.market_used?.data?.contractual_history?.requested_end
    || ''
}

export function sortValuationRuns(runs) {
  return [...runs].sort((left, right) => {
    const byDate = valuationDate(left).localeCompare(valuationDate(right))
    if (byDate) return byDate
    const byTime = String(left.created_at || '').localeCompare(String(right.created_at || ''))
    if (byTime) return byTime
    return Number(left.id || 0) - Number(right.id || 0)
  })
}

export function movementSeries(runs) {
  const ordered = sortValuationRuns(runs)
  return ordered.map((run, index) => {
    const value = mtmValue(run)
    const previous = index ? mtmValue(ordered[index - 1]) : null
    return {
      run,
      value,
      deltaPts: Number.isFinite(value) && Number.isFinite(previous)
        ? Math.round((value - previous) * 100 * 1e10) / 1e10
        : null,
    }
  })
}
