// « Modèles de produits » : the generic product catalogue and the generation
// of a Pricer session from one sheet, an underlying count and a tenor.
//
// The catalogue itself is data (productCatalogue.json), shared with the server
// copy that tests every sheet — adding a payoff means adding a sheet, never
// touching a screen. This module only reads it and turns a choice into the
// values the Pricer store expects.

import catalogue from '../data/productCatalogue.json'

export const PRODUCT_MODEL_TENORS = catalogue.tenors
export const PRODUCT_MODEL_FAMILIES = catalogue.families
export const productModels = catalogue.products.map(product => ({
  ...product,
  script: product.script.join('\n'),
}))

export function findProductModel(key) {
  return productModels.find(product => product.key === key) || null
}

export function findTenor(code) {
  return PRODUCT_MODEL_TENORS.find(tenor => tenor.code === code) || null
}

/** The tenors a sheet allows, in the catalogue's order. */
export function tenorsFor(model) {
  return PRODUCT_MODEL_TENORS.filter(tenor => model?.tenors?.includes(tenor.code))
}

/** Every underlying count a sheet allows, from its minimum to its maximum. */
export function underlyingCountsFor(model, maxAllowed = Infinity) {
  const min = Math.max(1, model?.underlyings?.min || 1)
  const max = Math.min(model?.underlyings?.max || min, maxAllowed)
  return Array.from({ length: Math.max(0, max - min + 1) }, (_, i) => min + i)
}

/**
 * An ISO date moved by whole months, clamped to the end of the target month —
 * the server's `relativedelta(months=n)`, so a 31 January strike gives a
 * 28 February observation rather than a 3 March one.
 */
export function addMonthsIso(iso, months) {
  const [year, month, day] = String(iso).split('-').map(Number)
  const total = (month - 1) + months
  const targetYear = year + Math.floor(total / 12)
  const targetMonth = ((total % 12) + 12) % 12
  const lastDay = new Date(Date.UTC(targetYear, targetMonth + 1, 0)).getUTCDate()
  const pad = value => String(value).padStart(2, '0')
  return `${targetYear}-${pad(targetMonth + 1)}-${pad(Math.min(day, lastDay))}`
}

function tenorPair(code) {
  const match = /^(\d+)([DWMY])$/i.exec(String(code || ''))
  return match ? { value: Number(match[1]), unit: match[2].toUpperCase() } : null
}

/**
 * The calendars of a sheet, generated from the strike date over the tenor.
 *
 * - `observations`: a schedule from the strike to strike + tenor, rolled on the
 *   strike, at the sheet's frequency;
 * - `maturity`: one date at strike + tenor;
 * - `strike_window`: the STRIKE_FIX departure window, on the strike date.
 *
 * No business-day convention and no settlement lag: a convention is typed from
 * the term sheet, it never gets a silent default. Windows keep the sheet's
 * lengths. Values come back in the store's shape — tenors as {value, unit}.
 */
export function buildModelCalendars(model, { strikeDate, tenorCode }) {
  const tenor = findTenor(tenorCode)
  if (!model || !tenor || !/^\d{4}-\d{2}-\d{2}$/.test(String(strikeDate || ''))) return null
  const maturity = addMonthsIso(strikeDate, tenor.months)
  const constats = {}
  for (const [name, spec] of Object.entries(model.constats || {})) {
    const windows = {
      ...(spec.window_length ? { window_length: tenorPair(spec.window_length) } : {}),
      ...(spec.window_frequency ? { window_frequency: tenorPair(spec.window_frequency) } : {}),
    }
    if (spec.role === 'observations') {
      constats[name] = {
        start_date: strikeDate, end_date: maturity, roll_date: strikeDate,
        frequency: tenorPair(spec.frequency), stub: 'short_last',
        convention: 'none', settlement_lag: 0, ...windows,
      }
    } else if (spec.role === 'maturity') {
      constats[name] = { date: maturity, ...windows }
    } else if (spec.role === 'strike_window') {
      constats[name] = { date: strikeDate, ...windows }
    }
  }
  return { maturity, constats }
}
