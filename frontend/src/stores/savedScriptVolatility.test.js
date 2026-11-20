// Un script enregistré rouvre avec la σ enregistrée (P1-10, constat du 19/11).
//
// Le catalogue de sous-jacents arrive après l'ouverture du script. Quand il
// reconnaît une action dans un sous-jacent resté « unknown », l'observateur de
// marketInputs.js pose la vol par défaut de sa classe (30 %) si la vol n'a pas
// d'origine. Un script enregistré par l'API, ou avant tout réglage de vol,
// rouvrait donc à 30 % au lieu de sa σ, et le premier pricing lancé entre-temps
// était écarté comme périmé.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { usePricingStore } from './pricing.js'
import { underlyingGroups } from '../data/commonUnderlyings.js'

const reply = data => ({ ok: true, json: async () => data })
const script = 'UNDERLYING Basket\nPARAM COUPON\nAT MATURITY\n  PAY COUPON'
const saved = underlyings => ({
  id: 5, name: 'RC enregistré', script_text: script, params_json: JSON.stringify({ COUPON: 8 }), constats_json: '{}',
  global_params_json: JSON.stringify({ configuration: { include_basket: true }, model: 'constant', underlyings,
    corr_matrix: underlyings.map((_, i) => underlyings.map((__, j) => (i === j ? 1 : 0.4))) }),
})

beforeEach(() => {
  setActivePinia(createPinia())
  underlyingGroups.splice(0)
  vi.stubGlobal('fetch', vi.fn(async url => reply(String(url).includes('/api/parse')
    ? { ok: true, params: [{ name: 'COUPON', kind: 'scalar', is_pct: true }], constats: [] } : {})))
})
afterEach(() => { underlyingGroups.splice(0); vi.unstubAllGlobals() })

async function catalogArrives() {
  underlyingGroups.push({ group: 'Actions France', items: [{ ticker: 'AIR.PA', label: 'Airbus', ccy: 'EUR', asset_class: 'equity' }] })
  await nextTick()
}

describe('vol d’un script enregistré', () => {
  it('garde la σ enregistrée quand le catalogue reconnaît une action', async () => {
    const store = usePricingStore()
    await store.loadFromDb(saved([{ name: 'S1', ticker: 'AIR.PA', ccy: 'EUR', sigma: 23, q: 2 }]), { scope: 'all' })
    expect(store.underlyings[0]).toMatchObject({ sigma: 23, vol_level_source: 'saved', _smileDefaults: false })
    await catalogArrives()
    expect(store.underlyings[0].sigma).toBe(23)
  })

  it('garde une origine explicite telle quelle', async () => {
    const store = usePricingStore()
    await store.loadFromDb(saved([
      { name: 'S1', ticker: 'AIR.PA', ccy: 'EUR', sigma: 31.5, vol_level_source: 'manual' },
      { name: 'S2', ticker: 'SAN.PA', ccy: 'EUR', sigma: 19.2, vol_level_source: 'realized' },
    ]), { scope: 'all' })
    expect(store.underlyings.map(u => u.vol_level_source)).toEqual(['manual', 'realized'])
  })

  it('un sous-jacent nouveau prend toujours la vol de sa classe', async () => {
    const store = usePricingStore()
    store.underlyings[0].ticker = 'AIR.PA'
    expect(store.underlyings[0].vol_level_source).toBe('default')
    await catalogArrives()
    expect(store.underlyings[0].sigma).toBe(30)
  })
})
