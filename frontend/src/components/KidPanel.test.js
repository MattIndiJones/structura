import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createRenderer, ssrContextKey } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import KidPanel from './KidPanel.vue'
import { usePricingStore } from '../stores/pricing.js'

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock('../utils/api.js', () => ({ apiFetch: (...args) => mocks.fetch(...args) }))
const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
let app, state, store
beforeEach(() => {
  vi.useFakeTimers()
  setActivePinia(createPinia())
  store = usePricingStore()
  store.currentProduct = { product_id: 3, terms_version: 2 }
  store.kid = { sri: 4, mrm: 4, crm: 2, vev: 15, T_rhp: 1, horizons: [], costs: {},
    calculation_receipt: { version: 1, server_signature: 'server-evidence', result: { sri: 4 } } }
  mocks.fetch.mockReset()
  app = renderer.createApp({ setup(_, context) { state = KidPanel.setup({}, context); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.mount({})
})
afterEach(() => { app?.unmount(); vi.clearAllTimers(); vi.useRealTimers() })

it('conserve la preuve serveur du calcul avec les chiffres envoyés à la sauvegarde', async () => {
  mocks.fetch.mockResolvedValue({ ok: true, json: async () => ({ id: 1 }) })
  await state.saveKid()
  expect(mocks.fetch).toHaveBeenCalledOnce()
  const [url, options] = mocks.fetch.mock.calls[0]
  expect(url).toBe('/api/kid/save')
  expect(JSON.parse(options.body)).toMatchObject({ product_id: 3, product_terms_version: 2,
    sri: 4, calculation_receipt: store.kid.calculation_receipt })
  expect(state.saveConfirm.value).toBe(true)
})

it('affiche le refus de preuve sans annoncer une conservation réussie', async () => {
  mocks.fetch.mockResolvedValue({ ok: false, status: 422,
    json: async () => ({ detail: 'Les termes ont changé. Recalculez le KID.' }) })
  await state.saveKid()
  expect(state.saveError.value).toContain('Recalculez le KID')
  expect(state.saveConfirm.value).toBe(false)
  expect(state.saving.value).toBe(false)
})
