import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, ssrContextKey } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import VariantCompareTab from './VariantCompareTab.vue'
import { usePricingStore } from '../stores/pricing.js'

const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
const reply = data => ({ ok: true, json: async () => data })
let app, state, store
async function mount({ reuse = false } = {}) {
  if (!reuse) { setActivePinia(createPinia()); store = usePricingStore(); store.currentScriptId = 12 }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/test', component: { render: () => null } }] })
  await router.push('/test'); await router.isReady()
  app = renderer.createApp({ setup(_, ctx) { state = VariantCompareTab.setup({}, ctx); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.use(router); app.mount({})
  store.ensureScriptValidated = vi.fn(async () => true)
  store.inLifeBody = vi.fn(() => ({ script: 'AT MATURITY\n  PAY 1' }))
  for (let i = 0; i < 15; i++) await nextTick()
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async url => reply(String(url).endsWith('/variants')
    ? [{ id: 13, variant_mode: 'roll' }] : [])))
})
afterEach(() => { app?.unmount(); vi.unstubAllGlobals() })

describe('comparaison et reprise des hypothèses de roll', () => {
  it('envoie le bid, sa provenance et les coûts dans la commande de comparaison', async () => {
    await mount()
    Object.assign(state.financing, { exit_basis: 'observed_bid', bid_pct: 90,
      bid_source: 'Bank quote', bid_observed_at: '2026-06-14T10:00:00', entry_cost_points: 1, exit_cost_points: .5 })
    fetch.mockClear(); fetch.mockResolvedValue(reply({ comparison_schema_version: 2, lignes: [], N: 8000 }))
    await state.comparer()
    const payload = JSON.parse(fetch.mock.calls[0][1].body)
    expect(payload.parent_id).toBe(12)
    expect(payload.roll_financing).toMatchObject({ exit_basis: 'observed_bid', bid_pct: 90,
      bid_source: 'Bank quote', entry_cost_points: 1, exit_cost_points: .5 })
    expect(payload.roll_financing.bid_observed_at).toBe(new Date('2026-06-14T10:00:00').toISOString())
  })

  it('conserve la saisie au changement d’onglet puis au remontage', async () => {
    await mount()
    state.financing.exit_basis = 'model_haircut'; state.financing.haircut_points = 2
    state.N.value = 4000
    expect(store.variantComparisonInputs.values.haircut_points).toBe(2)
    app.unmount(); await mount({ reuse: true })
    expect(state.financing.haircut_points).toBe(2)
    expect(state.financing.exit_basis).toBe('model_haircut')
    expect(state.N.value).toBe(4000)
  })

  it('ne transporte pas les coûts vers un autre dossier source', async () => {
    await mount(); state.financing.entry_cost_points = 2
    store.currentScriptId = 99
    for (let i = 0; i < 15; i++) await nextTick()
    expect(state.financing.entry_cost_points).toBe(0)
    expect(store.variantComparisonInputs).toBeNull()
  })

  it('invalide les chiffres affichés et leur preuve après modification des coûts', async () => {
    await mount()
    state.resultat.value = { preview: { signature: 'old' }, comparison_schema_version: 2, lignes: [] }
    state.financing.entry_cost_points = 1
    expect(state.resultat.value).toBeNull()
    fetch.mockClear(); await state.figer()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('ignore une réponse calculée avant la modification du bid', async () => {
    await mount()
    let finish, started
    const ready = new Promise(resolve => { started = resolve })
    fetch.mockImplementation(async () => { started(); return new Promise(resolve => { finish = resolve }) })
    const pending = state.comparer()
    await ready
    state.financing.haircut_points = 2
    finish(reply({ comparison_schema_version: 2, lignes: [{ recovery_mean: 1.1 }], N: 8000 }))
    await pending
    expect(state.resultat.value).toBeNull()
    expect(state.financing.haircut_points).toBe(2)
  })

  it('réouvre les coûts archivés et les chiffres conservés sans relancer le moteur', async () => {
    await mount()
    const result = { comparison_schema_version: 2, N: 4000, lignes: [{ reinvested_notional: .75,
      recovery_mean: .9, plafond: .9 }] }
    state.archives.value = [{ archive_id: 'frozen', evidence: { result,
      request: { roll_financing: { exit_basis: 'model_haircut', haircut_points: 3, entry_cost_points: 1 } } } }]
    fetch.mockClear(); state.ouvrirArchive('frozen')
    expect(fetch).not.toHaveBeenCalled()
    expect(state.financing.haircut_points).toBe(3)
    expect(state.N.value).toBe(4000)
    expect(state.lignes.value).toEqual(result.lignes)
    expect(state.archiveId.value).toBe('frozen')
  })

  it('conserve les hypothèses d’une nouvelle comparaison reprise depuis une archive', async () => {
    await mount()
    state.financing.exit_basis = 'model_haircut'; state.financing.haircut_points = 2
    state.archives.value = [{ archive_id: 'frozen', evidence: {
      result: { comparison_schema_version: 2, lignes: [], N: 4000 },
      request: { roll_financing: { exit_basis: 'model_haircut', haircut_points: 3 } } } }]
    state.ouvrirArchive('frozen')
    fetch.mockResolvedValue(reply({ comparison_schema_version: 2, lignes: [], N: 4000 }))
    await state.comparer()
    expect(state.archiveId.value).toBeNull()
    expect(store.variantComparisonInputs.values.haircut_points).toBe(3)
    app.unmount(); await mount({ reuse: true })
    expect(state.financing.haircut_points).toBe(3)
  })
})
