import { expect, it } from 'vitest'
import { surfaceBenchmarkIssues } from './lsvDiagnostics.js'
it('sépare un levier qualifié du biais absolu sur la surface SSVI', () => {
  const c = { status: 'QUALIFIED', underlyings: [{ underlying: 'STM', controls: [
    { kind: 'digitale', error_bp: 2, half_ci95_bp: 1, limit_bp: 10,
      lsv_vs_surface_bp: 46, lsv_half_ci95_bp: 9 },
    { kind: 'vanille', error_bp: 1, half_ci95_bp: 1, limit_bp: 5,
      lsv_vs_surface_bp: 3, lsv_half_ci95_bp: 2 },
  ] }] }
  expect(surfaceBenchmarkIssues(c)).toHaveLength(1)
  expect(surfaceBenchmarkIssues(c)[0].underlying).toBe('STM')
  expect(surfaceBenchmarkIssues(null)).toEqual([])
  expect(surfaceBenchmarkIssues({ underlyings: [{ controls: [{ limit_bp: 5 }] }] })).toEqual([])
})
