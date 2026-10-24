// Every displayed amount retains its currency; no implicit FX conversion.
export function currencyAmountLines(amounts, format) {
  return Object.entries(amounts || {}).sort(([a], [b]) => a.localeCompare(b))
    .filter(([, amount]) => Number.isFinite(amount))
    .map(([currency, amount]) => `${format(amount)} ${currency}`)
}

export function ticketRangeEntries(ranges) {
  if (ranges?.ticket_by_currency) return Object.entries(ranges.ticket_by_currency)
  return ranges?.ticket?.currency ? [[ranges.ticket.currency, ranges.ticket]] : []
}

export function ticketObservationText(ranges, format) {
  return ticketRangeEntries(ranges).filter(([, range]) => range.n > 0).map(([currency, range]) => {
    const values = [...new Set((range.points || []).map(format))]
    const amount = values.length ? (values.length === 1 ? values[0] : `${values[0]} – ${values.at(-1)}`) : format(range.median)
    return `${amount} ${currency}`
  }).join(' · ')
}
