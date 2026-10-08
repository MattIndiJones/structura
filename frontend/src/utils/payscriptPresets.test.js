import { describe, expect, it } from 'vitest'
import { preparePreset, payscriptPresets } from './payscriptPresets.js'
import { productModels } from './productModels.js'
import { parameterValues, serializeCalendars, usesAbsoluteSpots } from './payscriptEconomics.js'

import { presetServer as server } from './__fixtures__/payscriptPresetServer.js'

describe('exemples préremplis', () => {
  it.each(payscriptPresets)('$label fournit les termes complets, avec première observation distincte du fixing', async preset => {
    const fetcher = server()
    const plan = await preparePreset(preset.key, { startDate: '2026-10-07', currency: 'CHF' }, fetcher)
    const declarations = plan.validation.data
    const values = parameterValues(declarations.params, plan.params)
    expect(plan.validation.script).toBe(plan.model.script)
    expect(plan.observations[0] > plan.strikeDate).toBe(true)
    expect(plan.paymentDate > plan.maturityDate).toBe(true)
    expect(plan.currency).toBe('CHF')
    for (const p of declarations.params) {
      expect(values[p.name]).toEqual(Array.isArray(preset.params[p.name])
        ? preset.params[p.name].map(v => v / 100) : preset.params[p.name] / 100)
    }
    const serialized = serializeCalendars(declarations.constats, plan.constats, plan.strikeDate)
    for (const c of declarations.constats.filter(c => c.kind === 'schedule')) {
      expect(serialized[c.name]).toMatchObject({ convention: 'following', settlement_lag: 3, period_start_date: plan.strikeDate })
      expect(typeof serialized[c.name].frequency).toBe('string')
      expect(serialized[c.name].start_date).toBeUndefined()
    }
    expect(fetcher.mock.calls.filter(([url]) => url.includes('calendar') || url.includes('schedule'))
      .every(([, options]) => JSON.parse(options.body).currency === 'CHF')).toBe(true)
  })

  it('ajuste un départ samedi avant de construire la première observation et garde les barrières dégressives', async () => {
    const plan = await preparePreset('autocall_stepdown_5y', { startDate: '2026-01-31' }, server())
    expect(plan.strikeDate).toBe('2026-02-02')
    expect(plan.constats.OBSERVATIONDATES.first_observation_date).toBe('2027-02-02')
    expect(plan.params.M_AC_BAR).toEqual([100, 95, 90, 85, 80])
    expect(plan.observations).toHaveLength(5)
  })

  it('ne charge pas un exemple dont les dates ou le contrat ne peuvent pas être validés', async () => {
    await expect(preparePreset('autocall_3y', { startDate: '2026-10-07' }, server({ refuse: '/api/calendar/resolve' })))
      .rejects.toThrow('Calendrier indisponible')
    await expect(preparePreset('autocall_3y', { startDate: '2026-10-07' }, server({ extraParam: true })))
      .rejects.toThrow('ne correspondent plus au modèle')
  })
})

describe('cours absolus affichés selon le script', () => {
  it('ne demande aucun cours en devise pour les dix-neuf modèles génériques', () => {
    for (const model of productModels) expect(usesAbsoluteSpots(model.script), model.key).toBe(false)
  })
  it('reconnaît le ratio normalisé et ignore le fixing initial ainsi que les commentaires', () => {
    expect(usesAbsoluteSpots('UNDERLYING Basket\nAT StartDate:\n Basket.spot0 = Basket.spot@StartDate\n# Basket.spot\nSET PERF = WORSTOF(Basket.spot / Basket.spot0)')).toBe(false)
  })
  it.each(['Basket.spot', 'Basket.spot[1]', 'Basket.spot0'])('ouvre les cours pour un usage absolu de %s', member => {
    expect(usesAbsoluteSpots(`UNDERLYING Basket\nPAY ${member} * 100`)).toBe(true)
  })
})
