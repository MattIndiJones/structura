import { expect, it } from 'vitest'
import { bookedGrid, valuationGridWarning } from './simulationGrid.js'
it('lit le reçu de pricing avant les champs historiques et garde 52 pour les anciens deals', () => {
  expect(bookedGrid()).toBe(52)
  expect(bookedGrid({ stepsPerYear: 104 })).toBe(104)
  expect(bookedGrid({ stepsPerYear: 52, pricing_input: { steps_per_year: 208 } })).toBe(208)
  expect(valuationGridWarning(104, 52)).toBe('Deal booké à 104 pas/an. Cette valorisation utilise 52 pas/an.')
  expect(valuationGridWarning(104, 104)).toBe('')
})
