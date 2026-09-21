import { describe, expect, it } from 'vitest'
import { dealRiskState, localTodayIso } from './riskDates.js'

describe('périmètre de risque daté', () => {
  const deal = {
    trade_date: '2026-01-10',
    risk_terminal_date: '2026-06-15',
    status: 'callé',
  }

  it('grise un deal avant son booking et dès son événement terminal', () => {
    expect(dealRiskState(deal, '2026-01-09').active).toBe(false)
    expect(dealRiskState(deal, '2026-01-10').active).toBe(true)
    expect(dealRiskState(deal, '2026-06-14').active).toBe(true)
    expect(dealRiskState(deal, '2026-06-15').active).toBe(false)
  })

  it('formate la date locale sans conversion UTC', () => {
    expect(localTodayIso(new Date(2026, 8, 19, 23, 30))).toBe('2026-09-19')
  })
})
