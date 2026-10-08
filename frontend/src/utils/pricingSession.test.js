import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePricingStore } from '../stores/pricing.js'
import { openPricingSession } from './pricingSession.js'
import { preparePreset } from './payscriptPresets.js'
import { presetServer } from './__fixtures__/payscriptPresetServer.js'

describe('navigation et session de pricing', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    globalThis.fetch = presetServer()
  })

  it('reprend un exemple modifié, son marché et son prix au retour au Pricer', async () => {
    const store = usePricingStore()
    const route = { query: { modele: 'autocall', sousJacents: '1', tenor: '3Y' } }
    const load = vi.fn(async () => store.loadFromPreset(
      await preparePreset('autocall_3y', { startDate: '2026-10-14', currency: 'EUR' }, presetServer())))
    await openPricingSession(store, route, load)
    store.paramOverrides.COUPON = 13
    store.underlyings[0].sigma = 31
    store.globalParams.valuation_date = '2026-10-07'
    store.result = { price: .9723 }
    store.leftTab = 'params'
    const before = JSON.stringify(store.pricingBody())

    expect(await openPricingSession(store, {}, load)).toBe(false)
    expect(await openPricingSession(store, route, load)).toBe(false)
    expect(load).toHaveBeenCalledTimes(1)
    expect(JSON.stringify(store.pricingBody())).toBe(before)
    expect(store.result.price).toBe(.9723)
    expect(store.leftTab).toBe('params')

    expect(await openPricingSession(store, { params: { productId: '42' } }, load)).toBe(true)
    expect(load).toHaveBeenCalledTimes(2)
    expect(store.paramOverrides.COUPON).toBe(10)
    expect(store.result).toBeNull()
  })

  it('ne recharge ni un deal ni une RFQ au retour sur leur lien', async () => {
    const store = usePricingStore()
    const load = vi.fn()
    for (const route of [{ query: { dealId: '7' } }, { query: { fromRfq: '8' } },
      { params: { variantId: '3' } }, { params: { id: '9' } }]) {
      expect(await openPricingSession(store, route, load)).toBe(true)
      expect(await openPricingSession(store, route, load)).toBe(false)
    }
    expect(load).toHaveBeenCalledTimes(4)
  })
})
