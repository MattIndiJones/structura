/**
 * Centralised number/date formatting - French conventions (espace milliers,
 * virgule decimale, JJ/MM/AAAA, "%" precede d'une espace). Every formatter
 * returns the em-dash placeholder for null/undefined/NaN/+-Infinity instead
 * of leaking those through to the UI as "null"/"undefined"/"NaN".
 * Formatting only - never rounds/mutates the underlying value, only its
 * displayed string.
 *
 * IMPORTANT: Intl/toLocaleString's fr-FR thousands separator is U+202F
 * (narrow no-break space) - at most UI font sizes/weights it renders as a
 * near-invisible sliver (a stat tile showing "13950000" instead of
 * "13 950 000"). Every grouped number below goes through frLocale(), which
 * normalizes U+202F/U+00A0 to a plain ASCII space so the grouping is always
 * visually legible, regardless of font.
 */

const BLANK = '—' // em-dash placeholder for missing/invalid values
const SPACE_BEFORE_UNIT = ' ' // non-breaking space, renders as a normal-width space

function frLocale(n, options) {
  return n.toLocaleString('fr-FR', options).replace(/[  ]/g, ' ')
}

function isBlank(value) {
  if (value === null || value === undefined || value === '') return true
  const n = Number(value)
  return !Number.isFinite(n)
}

/** Plain grouped number, e.g. formatNumber(1234567.891, 2) -> "1 234 567,89" */
export function formatNumber(value, decimals = 2) {
  if (isBlank(value)) return BLANK
  return frLocale(Number(value), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/** Integer count/quantity - grouped, no decimals (paths, deals, sous-jacents...) */
export function formatInt(value) {
  if (isBlank(value)) return BLANK
  return frLocale(Math.round(Number(value)))
}

export const formatQty = formatInt

/** Monetary amount with currency symbol, e.g. formatMoney(1234567.89) -> "1 234 567,89 EUR" */
export function formatMoney(value, currency = 'EUR', decimals = 2) {
  if (isBlank(value)) return BLANK
  return frLocale(Number(value), {
    style: 'currency',
    currency,
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/** Same as formatMoney but no decimals - for large round amounts (nominal, VaR/ES...) */
export function formatMoneyRound(value, currency = 'EUR') {
  return formatMoney(value, currency, 0)
}

/**
 * Same as formatPercent, but keeps whatever precision the value already has
 * (up to 3 decimals) instead of forcing a fixed count - for percentages a
 * backend endpoint already rounded server-side, where re-forcing a decimal
 * count client-side would either pad fake trailing zeros or re-round
 * differently than intended. Still fixes the locale (comma, space before %).
 */
export function formatPercentRaw(value) {
  if (isBlank(value)) return BLANK
  return `${frLocale(Number(value))}${SPACE_BEFORE_UNIT}%`
}

/** value already expressed in percentage points (12.45, not 0.1245) -> "12,45 %" */
export function formatPercent(value, decimals = 2) {
  if (isBlank(value)) return BLANK
  const n = frLocale(Number(value), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
  return `${n}${SPACE_BEFORE_UNIT}%`
}

/** value as a fraction (0.1245) - multiplies by 100 before formatting -> "12,45 %" */
export function formatFractionAsPercent(value, decimals = 2) {
  if (isBlank(value)) return BLANK
  return formatPercent(Number(value) * 100, decimals)
}

/**
 * Greeks/sensitivities - often small (gamma, vega...), more precision than
 * money by default. Falls back to scientific notation under 1e-4 (non-zero)
 * rather than printing a string of near-meaningless zeros.
 */
export function formatGreek(value, decimals = 4) {
  if (isBlank(value)) return BLANK
  const n = Number(value)
  if (n !== 0 && Math.abs(n) < 0.0001) {
    return frLocale(n, { notation: 'scientific', maximumFractionDigits: 2 })
  }
  return frLocale(n, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/** Basis points, e.g. formatBps(12.3) -> "12,3 bps" */
export function formatBps(value, decimals = 1) {
  if (isBlank(value)) return BLANK
  return `${formatNumber(value, decimals)}${SPACE_BEFORE_UNIT}bps`
}

function pad(n) {
  return String(n).padStart(2, '0')
}

const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/

function toDate(input) {
  if (!input) return null
  if (input instanceof Date) return Number.isNaN(input.getTime()) ? null : input
  // A bare "YYYY-MM-DD" (no time component) must be read as a LOCAL calendar
  // date - `new Date('YYYY-MM-DD')` parses it as UTC midnight instead, which
  // silently shifts the displayed day backward by one in negative-offset
  // timezones (e.g. the Americas).
  const dateOnly = DATE_ONLY_RE.exec(input)
  if (dateOnly) {
    const [, y, m, d] = dateOnly
    return new Date(Number(y), Number(m) - 1, Number(d))
  }
  const d = new Date(input)
  return Number.isNaN(d.getTime()) ? null : d
}

/** ISO date/datetime -> "28/07/2026" */
export function formatDate(input) {
  const d = toDate(input)
  if (!d) return BLANK
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`
}

/** ISO datetime -> "28/07/2026 09:35" */
export function formatDateTime(input) {
  const d = toDate(input)
  if (!d) return BLANK
  return `${formatDate(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
