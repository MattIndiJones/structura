import { describe, expect, it } from 'vitest'
import { aggregateDailyQuoteEdges, isHistoricalQuoteEligible } from './rfqAnalysis.js'

describe('C23 historical quote analysis', () => {
  it.each(['RESERVED', 'ROUND_CLOSED', 'EXPIRED'])('keeps a qualified historical %s quote', state => {
    expect(isHistoricalQuoteEligible({ origin: 'NETWORK', comparable: false, history_eligible: true,
      edge_bps: 100, publication: { state } })).toBe(true)
  })
  it.each([
    { history_eligible: false }, { superseded: true }, { edge_bps: null }, { edge_bps: NaN },
  ])('excludes unqualified or superseded observations %j', overrides => {
    expect(isHistoricalQuoteEligible({ edge_bps: 100, history_eligible: true, ...overrides })).toBe(false)
  })
  it('explicitly averages all same-day quotes without depending on input order', () => {
    const history = [
      { provider: 'A', date: '2026-10-21T10:00Z', edge_bps: 100 },
      { provider: 'A', date: '2026-10-21T11:00Z', edge_bps: -300 },
      { provider: 'B', date: '2026-10-22T10:00Z', edge_bps: 50 },
    ]
    const result = aggregateDailyQuoteEdges(history, ['A', 'B'])
    expect(result).toEqual(aggregateDailyQuoteEdges([...history].reverse(), ['A', 'B']))
    expect(result.labels).toEqual(['2026-10-21', '2026-10-22'])
    expect(result.series[0]).toEqual({ provider: 'A', values: [-100, null], counts: [2, 0] })
  })
})
