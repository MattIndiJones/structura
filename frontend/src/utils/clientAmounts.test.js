import { describe, expect, it } from 'vitest'
import { currencyAmountLines, ticketObservationText, ticketRangeEntries } from './clientAmounts.js'

describe('C24 monetary observations retain their units', () => {
  const format = value => (value / 1e6).toString() + ' M'
  it('renders EUR and JPY separately, never as a 101 M pipeline', () => {
    expect(currencyAmountLines({ JPY: 100e6, EUR: 1e6 }, format)).toEqual(['1 M EUR', '100 M JPY'])
  })
  it('includes currency even with a single amount or an explicit zero', () => {
    expect(currencyAmountLines({ EUR: 0 }, format)).toEqual(['0 M EUR'])
  })
  it('does not replace missing or non-finite amounts with zero', () => {
    expect(currencyAmountLines({ EUR: null, USD: NaN, JPY: Infinity }, format)).toEqual([])
  })
  it('renders two ticket ranges without a mixed-currency median', () => {
    expect(ticketObservationText({ ticket_by_currency: {
      EUR: { n: 1, points: [1e6] }, JPY: { n: 5, points: [], median: 100e6 },
    } }, format)).toBe('1 M EUR · 100 M JPY')
  })
  it('keeps multiple observations in their own currency', () => {
    expect(ticketObservationText({ ticket_by_currency: { EUR: { n: 2, points: [1e6, 3e6] } } }, format))
      .toBe('1 M – 3 M EUR')
  })
  it('does not assign a guessed currency to a legacy scalar', () => {
    expect(ticketRangeEntries({ ticket: { n: 1, points: [1e6] } })).toEqual([])
  })
  it('keeps declared-only ranges without inventing an observed ticket', () => {
    expect(ticketObservationText({ ticket_by_currency: { EUR: { n: 0, points: [], declared_min: 1e6 } } }, format)).toBe('')
  })
})
