import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, reactive, ssrContextKey } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import EventsTab from './EventsTab.vue'

const mocks = vi.hoisted(() => ({ auth: null, deals: null, fetch: vi.fn(), request: vi.fn() }))
vi.mock('../stores/auth.js', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('../stores/deals.js', () => ({ useDealsStore: () => mocks.deals }))
vi.mock('../utils/api.js', () => ({ apiFetch: (...args) => mocks.fetch(...args) }))
const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
let app, state
async function mount() {
  setActivePinia(createPinia())
  app = renderer.createApp({ setup(props, ctx) { state = EventsTab.setup({ initialDealId: null }, ctx); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.mount({})
  for (let i = 0; i < 5; i++) await nextTick()
}
beforeEach(() => {
  vi.useFakeTimers()
  mocks.auth = reactive({ user: { id: 7, role: 'ops_maker', installation: { kind: 'organization' },
    capabilities: ['operations.prepare'], amendment_four_eyes: false } })
  mocks.deals = reactive({ currentDeal: { id: 41, user_id: 8, counterparty_id: 1, events: [] }, deals: [],
    loadDeals: vi.fn().mockResolvedValue(), loadAudit: vi.fn().mockResolvedValue(), requestAmendment: mocks.request })
  mocks.request.mockReset(); mocks.request.mockResolvedValue({})
  mocks.fetch.mockReset(); mocks.fetch.mockResolvedValue({ ok: true, json: async () => [{ id: 1, name: 'Current bank' }, { id: 2, name: 'New bank' }] })
})
afterEach(() => { app?.unmount(); vi.clearAllTimers(); vi.useRealTimers() })

describe('amendements économiques gouvernés', () => {
  it('permet aux Opérations de préparer un dossier partagé et conserve les quatre yeux', async () => {
    await mount()
    expect(state.canPrepareAmendment.value).toBe(true)
    expect(state.canCheck({ field_name: 'nominal', requested_by: 7 })).toBe(true)
    mocks.auth.user.amendment_four_eyes = true
    expect(state.canCheck({ field_name: 'nominal', requested_by: 8 })).toBe(false)
    mocks.auth.user.capabilities = ['operations.validate']
    expect(state.canPrepareAmendment.value).toBe(false)
    expect(state.canCheck({ field_name: 'nominal', requested_by: 8 })).toBe(true)
    expect(state.canCheck({ field_name: 'nominal', requested_by: 7 })).toBe(false)
  })

  it('refuse la préparation par le Front et le Contrôle en installation gérée', async () => {
    mocks.auth.user.capabilities = ['business.read', 'business.price']
    await mount()
    Object.assign(state.amendmentForm, { new_value: '1400000', reason: 'Correction contractuelle motivée' })
    await state.createAmendment()
    expect(mocks.request).not.toHaveBeenCalled()
  })

  it('soumet l’identifiant juridique et retire le netting set de la banque source', async () => {
    await mount()
    state.amendmentForm.field_name = 'contrepartie'
    await state.onAmendmentFieldChange()
    expect(state.amendmentCounterparties.value).toEqual([{ id: 2, name: 'New bank' }])
    Object.assign(state.amendmentForm, { new_value: 2, reason: 'Transfert juridique documenté' })
    await state.createAmendment()
    expect(mocks.request).toHaveBeenCalledExactlyOnceWith(41, { field_name: 'contrepartie',
      new_value: { counterparty_id: 2, ccr_netting_set_id: null }, reason: 'Transfert juridique documenté' })
  })

  it('conserve le mode autonome propriétaire et refuse une valeur économique non finie', async () => {
    mocks.auth.user.installation = null
    mocks.deals.currentDeal.user_id = 7
    await mount()
    expect(state.canPrepareAmendment.value).toBe(true)
    Object.assign(state.amendmentForm, { new_value: 'Infinity', reason: 'Correction contractuelle motivée' })
    await state.createAmendment()
    expect(mocks.request).not.toHaveBeenCalled()
    expect(state.creditDecisionLabel('NO_LIMIT')).toContain('aucune limite')
  })
})
