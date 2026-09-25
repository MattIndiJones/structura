/**
 * The engine's delta is the price change for a 1% move of today's spot.
 * Convert it to a 1% move of the initial fixing without changing the risk Greek.
 */
export function strikeBasedDelta(currentSpotDelta, currentOverInitial) {
  if (!Number.isFinite(currentSpotDelta) || !Number.isFinite(currentOverInitial)
      || currentOverInitial <= 0) return null
  return currentSpotDelta / currentOverInitial
}

/** Add indicative rows for display only; leave the engine Greeks untouched. */
export function withIndicativeDeltas(entries, underlyings, { dated, spotRatios, preStrike }) {
  return entries.flatMap(entry => {
    const delta = entry.name.match(/^delta_(\d+)$/)
    if (!delta || preStrike) return [entry]
    const underlying = underlyings[Number(delta[1]) - 1]
    const ratio = dated === true ? spotRatios?.[underlying?.name]
      : dated === false ? 1 : undefined
    const indicative = strikeBasedDelta(entry.rawValue, ratio)
    return indicative == null ? [entry] : [
      entry,
      { name: `${entry.name}_strike`, sourceName: entry.name, rawValue: indicative,
        displayValue: indicative, indicative: true },
    ]
  })
}
