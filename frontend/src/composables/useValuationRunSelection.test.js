import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useValuationRunSelection, runSelectionWarnings } from './useValuationRunSelection'

const run = (id, date, model = 'constant') => ({ id, created_at: `${date}T12:00:00Z`, result: { mtm: 1, valuation_date: date, market_used: { source: 'booking', model } } })
describe('Selection of archived MtM for Valo Explain', () => {
  it('limits selection to two and orders by valuation date regardless of click order', () => {
    const s = useValuationRunSelection(ref([run(3, '2026-09-17'), run(2, '2026-09-16'), run(1, '2026-09-15')]))
    s.toggle(3); s.toggle(1); s.toggle(2)
    expect(s.selected.value.map(r => r.id)).toEqual([1, 3])
    s.invert()
    s.toggle(2)
    expect(s.selected.value.map(r => r.id)).toEqual([3, 1])
    s.toggle(3)
    expect(s.selected.value.map(r => r.id)).toEqual([1])
    s.reset()
    expect(s.selected.value).toEqual([])
  })
  it('restores the saved direction and rejects runs from another deal', () => {
    const rows = ref([run(1, '2026-09-15'), run(2, '2026-09-16')])
    const s = useValuationRunSelection(rows)
    s.reset([2, 1], true)
    expect(s.selected.value.map(r => r.id)).toEqual([2, 1])
    rows.value = [run(5, '2026-09-17')]
    s.reset([1, 5])
    expect(s.ids.value).toEqual([5])
  })
  it('flags differences in model, basis and recorded market parameters before generation', () => {
    const a = run(1, '2026-09-15'), b = run(2, '2026-09-16', 'heston')
    b.result.market_used.source = 'realized'
    b.result.market_used.r = 3
    const warnings = runSelectionWarnings([a, b])
    expect(warnings).toHaveLength(3)
    expect(warnings.join(' ')).toContain('sans attribution causale')
    expect(runSelectionWarnings([a])).toEqual([])
    expect(runSelectionWarnings([a, run(3, '2026-09-17')])).toEqual([])
  })
})
