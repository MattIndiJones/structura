import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, ssrContextKey } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import RfqView from './RfqView.vue'

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), fetchProduct: vi.fn() }))
vi.mock('../utils/api.js', () => ({ apiFetch: (...args) => mocks.fetch(...args) }))
vi.mock('../stores/products.js', () => ({ useProductsStore: () => ({ fetchOne: mocks.fetchProduct }) }))
const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
let app, state, router
const response = data => ({ ok: true, json: async () => data })
async function flush() { for (let i = 0; i < 14; i++) await nextTick() }
beforeEach(() => {
  setActivePinia(createPinia()); mocks.fetchProduct.mockReset(); mocks.fetch.mockReset()
  mocks.fetch.mockImplementation(async url => {
    if (url === '/api/parse') return response({ ok: true, params: [], constats: [] })
    if (url === '/api/rfq-desks') return response([{ id: 11, name: 'Structuration', rights: ['prepare'] }])
    if (url === '/api/clients') return response([{ id: 7, name: 'Client conservé' }])
    if (String(url).includes('/mandates')) return response([{ id: 8, name: 'Mandat conservé' }])
    return response([])
  })
})
afterEach(() => { app?.unmount(); app = null })
async function mount() {
  router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/rfq', component: { render: () => null } }] })
  await router.push('/rfq'); await router.isReady()
  app = renderer.createApp({ setup(props, ctx) { state = RfqView.setup({}, ctx); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.use(router); app.mount({}); await flush()
}
const product = {
  product_id: 42, reference: 'PRD-C06', terms_version: 2, name: 'Produit conservé',
  intent: { side: 'SELL', nominal: 2_000_000, transaction_format: 'OTC', instrument_family: 'Swap',
    payoff_family: 'Autocall', documentation_reference: 'ISDA C06' },
  commercial: { client_id: 7, mandate_id: 8, opportunity_id: null, primary_affiliation_id: null },
  terms: { script: 'AT MATURITY\n  PAY 1', T: 1, settlement_ccy: 'EUR', strike_date: '2026-10-20',
    value_date: '2026-10-22', maturity_date: '2027-10-20', payment_date: '2027-10-25',
    parameters: [], constats: {}, underlyings: [{ name: 'A', ticker: 'A', ccy: 'EUR' }] },
}

describe('Product vers RFQ', () => {
  it('remplace l’intention de création Product par le lien du dossier RFQ sélectionné', async () => {
    await mount()
    await router.replace('/rfq?product=42')
    const dossier = { id: 6, params: { underlyings: [], T: 1 }, quotes: [] }
    vi.spyOn(state.rfq, 'fetchOne').mockImplementation(async () => {
      state.rfq.current = dossier
      return dossier
    })
    await state.selectRfq(6)
    expect(router.currentRoute.value.fullPath).toBe('/rfq?rfq=6')
    expect(state.selectedId.value).toBe(6)
    expect(state.showCreateForm.value).toBe(false)
    expect(state.rfq.current.id).toBe(6)
  })

  it('préremplit vente, deux millions, Client, mandat et documentation OTC', async () => {
    mocks.fetchProduct.mockResolvedValue({ product: structuredClone(product), calculationInput: null })
    await mount(); await state.prefillFromProduct(42); await flush()
    expect(state.form).toMatchObject({ sens: 'vente', client_id: 7, mandate_id: 8,
      transaction_format: 'OTC', instrument_family: 'Swap', payoff_family: 'Autocall', documentation_reference: 'ISDA C06' })
    expect(state.nominalValue.value).toBe(2_000_000)
    expect(state.commercialLinkEnabled.value).toBe(true)
    expect(state.sourceProduct.value.terms_version).toBe(2)
    expect(state.directClients.value).toContainEqual({ id: 7, name: 'Client conservé' })
  })

  it('préserve aussi le sens achat et un dossier sans contexte Client', async () => {
    mocks.fetchProduct.mockResolvedValue({ product: { ...structuredClone(product), intent: { side: 'BUY', nominal: 3_000_000 }, commercial: {} }, calculationInput: null })
    await mount(); await state.prefillFromProduct(42); await flush()
    expect(state.form.sens).toBe('achat')
    expect(state.form.client_id).toBeNull()
    expect(state.commercialLinkEnabled.value).toBe(false)
    expect(state.nominalValue.value).toBe(3_000_000)
  })

  it('le bouton de pricing envoie les hypothèses sans identité du sous-jacent', async () => {
    await mount()
    state.rfq.current = { id: 6, script_snapshot: 'AT MATURITY\n  PAY 1',
      params: { T: 1, currency: 'EUR', underlyings: [{ name: 'A', ticker: 'A', ccy: 'EUR', sigma: .2, q: .01 }] } }
    await state.refreshDetailParams()
    const update = vi.spyOn(state.rfq, 'update').mockResolvedValue()
    vi.spyOn(state.rfq, 'computeModelPrice').mockResolvedValue()
    await state.computeModelPrice()
    expect(state.computeError.value).toBe('')
    expect(update).toHaveBeenCalledTimes(1)
    const payload = update.mock.calls[0][1].pricing_params
    expect(payload.underlyings[0].sigma).toBe(.2)
    for (const key of ['name', 'ticker', 'ccy']) expect(payload.underlyings[0]).not.toHaveProperty(key)
    for (const key of ['T', 'constats', 'payment_date', 'frozen_schedule']) expect(payload).not.toHaveProperty(key)
  })
})
