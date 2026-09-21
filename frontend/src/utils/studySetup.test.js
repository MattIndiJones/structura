import { describe, it, expect } from 'vitest'
import { configurationFromManifest } from './studySetup'
import { restoreStudyArtifacts } from './studySnapshot'

describe('Complete study setup', () => {
  it('preserves a local benchmark and momentum after scanning', () => {
    const setup = configurationFromManifest({ params: { benchmark_ticker: 'SYNTH_BENCH20_USD',
      ff_series: 'Developed_5F_MOM', selected_factors: ['Mkt-RF', 'MOM'], rolling_window: 120 } }, [{ ticker: 'ACWI' }])
    expect(setup.customTicker).toBe('SYNTH_BENCH20_USD')
    expect(setup.config).toEqual({ benchmark_ticker: 'CUSTOM', ff_series: 'Developed_5F_MOM',
      selected_factors: ['Mkt-RF', 'MOM'], rolling_window: 120 })
  })
  it('keeps known benchmarks and derives factors when omitted', () => {
    expect(configurationFromManifest({ params: { factor_model: 'FF3' } }, [{ ticker: 'ACWI' }]))
      .toEqual({ customTicker: '', config: { benchmark_ticker: 'ACWI', ff_series: 'Developed_5F',
        selected_factors: ['Mkt-RF', 'SMB', 'HML'], rolling_window: 60 } })
  })
  it('restores the automatically computed Brinson result', () => {
    expect(restoreStudyArtifacts({ block_g: { available: true, active_return_pct: -13.54 } }).brinson.active_return_pct).toBe(-13.54)
  })
  it('keeps ISIN suggestions only when no benchmark is declared', () => {
    const manifest = { product: { isin: 'TEST' }, params: { benchmark_ticker: '<À COMPLÉTER>' } }
    expect(configurationFromManifest(manifest, [], { TEST: 'SUGGESTED' }).customTicker).toBe('SUGGESTED')
    manifest.params.benchmark_ticker = 'LOCAL'
    expect(configurationFromManifest(manifest, [], { TEST: 'SUGGESTED' }).customTicker).toBe('LOCAL')
  })
})
