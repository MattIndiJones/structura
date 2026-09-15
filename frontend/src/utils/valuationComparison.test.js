import { describe, expect, it } from 'vitest'
import {
  movementSeries, sortValuationRuns, valuationDate,
} from './valuationComparison.js'

function run(id, valuationDateValue, mtm, createdAt, recalibrate = 'realized', version = 1) {
  return {
    id, created_at: createdAt, contract_version: version,
    diagnostics: { request: { valuation_date: valuationDateValue, recalibrate } },
    result: { mtm },
  }
}

describe('comparaison des valorisations', () => {
  it('ordonne par date de valorisation puis par heure de calcul', () => {
    const second = run(2, '2026-09-15', .91, '2026-09-15T12:00:00')
    const first = run(1, '2026-09-14', .90, '2026-09-15T13:00:00')
    const third = run(3, '2026-09-15', .92, '2026-09-15T13:00:00')
    expect(sortValuationRuns([third, second, first]).map(item => item.id)).toEqual([1, 2, 3])
  })

  it('calcule chaque mouvement contre la date sélectionnée précédente', () => {
    const series = movementSeries([
      run(3, '2026-09-16', .94, '2026-09-16T10:00:00'),
      run(1, '2026-09-14', .90, '2026-09-14T10:00:00'),
      run(2, '2026-09-15', .91, '2026-09-15T10:00:00'),
    ])
    expect(series.map(item => item.deltaPts)).toEqual([null, 1, 3])
  })

  it('retrouve la date de valorisation conservée dans le résultat', () => {
    expect(valuationDate({ result: { valuation_date: '2026-09-14' } })).toBe('2026-09-14')
  })
})
