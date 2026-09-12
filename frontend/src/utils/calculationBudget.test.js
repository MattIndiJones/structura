import { describe, expect, it } from 'vitest'
import { estimatePricingCalculation } from './calculationBudget.js'

const base = {
  script: 'AT MATURITY:\n  PAY 1', maturityYears: 3, underlyings: 2,
  paths: 20_000, model: 'constant', antithetic: true,
}

describe('estimation du coût de pricing', () => {
  it('ajoute le coût des Greeks sans empiler leur mémoire', () => {
    const prix = estimatePricingCalculation(base)
    const avecGreeks = estimatePricingCalculation({
      ...base, selectedGreeks: ['delta', 'gamma', 'vega', 'theta', 'rho', 'corr'],
    })
    expect(avecGreeks.workUnits).toBeGreaterThan(prix.workUnits)
    expect(avecGreeks.peakBytes).toBe(prix.peakBytes)
  })

  it('bloque les dimensions au-delà des limites serveur', () => {
    expect(estimatePricingCalculation({ ...base, maturityYears: 31 }).blocked).toBe(true)
    expect(estimatePricingCalculation({ ...base, underlyings: 13 }).blocked).toBe(true)
    expect(estimatePricingCalculation({ ...base, script: 'x'.repeat(32_001) }).blocked).toBe(true)
  })

  it('intègre les dates littérales développées au coût', () => {
    const unique = estimatePricingCalculation(base)
    const dense = estimatePricingCalculation({ ...base, script: 'AT 0.1..3:0.1:\n  PAY 1' })
    expect(dense.expandedDates).toBe(30)
    expect(dense.workUnits).toBeGreaterThan(unique.workUnits)
  })
})
