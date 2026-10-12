import { describe, expect, it } from 'vitest'
import { previousLocalYearDate } from './workshopDate'

describe('workshop calendar', () => {
  it('uses the local day just after midnight', () => {
    expect(previousLocalYearDate(new Date(2026, 9, 9, 0, 15))).toBe('2025-10-09')
  })
  it('clamps leap day to the previous February', () => {
    expect(previousLocalYearDate(new Date(2028, 1, 29, 0, 15))).toBe('2027-02-28')
  })
})
