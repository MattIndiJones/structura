/**
 * Le module « Modèles de produits » génère des dates qui partent au moteur :
 * la même arithmétique que le serveur, ou des constatations décalées d'un jour
 * qu'aucun écran ne signale.
 */
import { describe, expect, it } from 'vitest'

import {
  PRODUCT_MODEL_TENORS, addMonthsIso, buildModelCalendars, findProductModel,
  productModels, tenorsFor, underlyingCountsFor,
} from './productModels.js'

describe('addMonthsIso suit relativedelta(months=n)', () => {
  it.each([
    ['2026-09-14', 36, '2029-09-14'],
    ['2026-09-14', 18, '2028-03-14'],
    ['2026-01-31', 1, '2026-02-28'],
    ['2028-02-29', 12, '2029-02-28'],
    ['2026-12-31', 6, '2027-06-30'],
    ['2026-11-30', 120, '2036-11-30'],
  ])('%s + %i mois = %s', (start, months, expected) => {
    expect(addMonthsIso(start, months)).toBe(expected)
  })
})

describe('le catalogue', () => {
  it('propose les ténors M9, dans l’ordre', () => {
    expect(PRODUCT_MODEL_TENORS.map(t => t.code))
      .toEqual(['6M', '1Y', '18M', '2Y', '3Y', '4Y', '5Y', '7Y', '10Y'])
  })

  it('donne à chaque fiche un script sans date et des rôles connus', () => {
    for (const model of productModels) {
      expect(model.script).not.toMatch(/^AT\s+\d/m)
      for (const spec of Object.values(model.constats)) {
        expect(['observations', 'maturity', 'strike_window']).toContain(spec.role)
      }
      expect(tenorsFor(model).length).toBe(model.tenors.length)
    }
  })

  it('borne le nombre de sous-jacents par fiche', () => {
    expect(underlyingCountsFor(findProductModel('autocall_athena'))).toEqual([1, 2, 3, 4, 5])
    expect(underlyingCountsFor(findProductModel('call_panier_moyenne'))).toEqual([2, 3, 4, 5])
    expect(underlyingCountsFor(findProductModel('autocall_athena'), 3)).toEqual([1, 2, 3])
  })
})

describe('buildModelCalendars', () => {
  it('génère un échéancier du strike à la maturité, ancré sur le strike', () => {
    const plan = buildModelCalendars(findProductModel('autocall_athena'),
      { strikeDate: '2026-09-14', tenorCode: '3Y' })

    expect(plan.maturity).toBe('2029-09-14')
    expect(plan.constats.OBSERVATIONS).toEqual({
      start_date: '2026-09-14', end_date: '2029-09-14', roll_date: '2026-09-14',
      frequency: { value: 1, unit: 'Y' }, stub: 'short_last',
      convention: 'none', settlement_lag: 0,
    })
  })

  it('pose la fenêtre de départ au strike et la date unique à maturité', () => {
    const plan = buildModelCalendars(findProductModel('call_panier_moyenne'),
      { strikeDate: '2026-09-14', tenorCode: '18M' })

    expect(plan.constats.STRIKE_FIX).toEqual({
      date: '2026-09-14',
      window_length: { value: 10, unit: 'D' }, window_frequency: { value: 1, unit: 'D' },
    })
    expect(plan.constats.MATURITE).toEqual({
      date: '2028-03-14',
      window_length: { value: 30, unit: 'D' }, window_frequency: { value: 1, unit: 'D' },
    })
  })

  it('porte la fréquence de relevé d’une fenêtre de période', () => {
    const plan = buildModelCalendars(findProductModel('autocall_coupon_moyenne_periode'),
      { strikeDate: '2026-09-14', tenorCode: '2Y' })

    expect(plan.constats.OBSERVATIONS.window_frequency).toEqual({ value: 3, unit: 'M' })
  })

  it('ne génère rien sans strike ou sans ténor connu', () => {
    const model = findProductModel('call')
    expect(buildModelCalendars(model, { strikeDate: '', tenorCode: '1Y' })).toBeNull()
    expect(buildModelCalendars(model, { strikeDate: '2026-09-14', tenorCode: '9Y' })).toBeNull()
  })
})
