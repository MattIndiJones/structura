export const GRID_FREQUENCIES = [52, 104, 208]

export function bookedGrid(market = {}) {
  const value = Number(market.pricing_input?.steps_per_year ?? market.steps_per_year ?? market.stepsPerYear ?? 52)
  return GRID_FREQUENCIES.includes(value) ? value : 52
}

export function valuationGridWarning(booked, effective) {
  return booked === effective ? '' : `Deal booké à ${booked} pas/an. Cette valorisation utilise ${effective} pas/an.`
}
