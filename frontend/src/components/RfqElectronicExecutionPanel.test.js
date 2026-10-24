import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, h, nextTick, reactive, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import Panel from './RfqElectronicExecutionPanel.vue'

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), refresh: vi.fn(), request: vi.fn() }))
vi.mock('../utils/api.js', () => ({ apiFetch: (...args) => mocks.fetch(...args), apiErrorMessage: data => data.detail }))
vi.mock('../stores/rfq.js', () => ({ useRfqStore: () => ({ fetchOne: mocks.refresh, requestElectronicExecution: mocks.request }) }))
const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
const response = data => ({ ok: true, json: async () => data })
const deferred = () => { let resolve, reject; const promise = new Promise((r, j) => { resolve = r; reject = j }); return { promise, resolve, reject } }
const received = (id = 1) => ({ id, rights: ['read', 'book'], electronic_execution: {
  id: 'execution-' + id, request_hash: 'a'.repeat(64), state: 'RECEIVED', execution_reference: 'EXE-TEST',
  quote: { price: 98.5, nominal: 1000000, currency: 'EUR', revision: 2 },
} })
let app, state, emit
async function mount(props) {
  emit = vi.fn()
  app = renderer.createApp({ setup(_, ctx) { state = Panel.setup(props, { ...ctx, emit }); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.mount({})
  await nextTick()
}
beforeEach(() => { setActivePinia(createPinia()); mocks.fetch.mockReset(); mocks.refresh.mockReset(); mocks.request.mockReset() })
afterEach(() => app?.unmount())

describe('décision bancaire électronique', () => {
  it('conserve la revue et le motif pendant une actualisation du même dossier', async () => {
    const props = reactive({ received: received(), contextRevision: 3 })
    await mount(props); state.opened.value = true; state.reviewed.value = true; state.reason.value = 'Revue en cours'
    props.received = received(); await nextTick()
    expect(state.opened.value).toBe(true); expect(state.reviewed.value).toBe(true)
    expect(state.reason.value).toBe('Revue en cours')
  })
  it('exige droit book, revue explicite et motif avant tout envoi', async () => {
    const props = reactive({ received: received(), contextRevision: 1 })
    await mount(props)
    await state.send('CONFIRMED'); expect(mocks.fetch).not.toHaveBeenCalled()
    state.reviewed.value = true; await state.send('CONFIRMED'); expect(mocks.fetch).not.toHaveBeenCalled()
    state.reason.value = 'Accord bancaire vérifié'; props.received.rights = ['read', 'publish_quote']
    await state.send('CONFIRMED'); expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('transmet l’empreinte exacte et rend le dossier au contexte bancaire courant', async () => {
    const props = reactive({ received: received(), contextRevision: 7 })
    await mount(props); state.opened.value = true; state.reviewed.value = true; state.reason.value = 'Accord vérifié'
    const updated = { ...received(), electronic_execution: { ...received().electronic_execution, state: 'CONFIRMED' } }
    mocks.fetch.mockResolvedValueOnce(response(updated))
    await state.send('CONFIRMED')
    expect(JSON.parse(mocks.fetch.mock.calls[0][1].body)).toEqual({ expected_request_hash: 'a'.repeat(64), decision: 'CONFIRMED', reason: 'Accord vérifié' })
    expect(emit).toHaveBeenCalledWith('updated', updated, 7)
    expect(state.opened.value).toBe(false)
  })

  it.each([false, true])('ignore une décision tardive après réouverture, autre dossier=%s', async other => {
    const props = reactive({ received: received(), contextRevision: 3 })
    await mount(props); state.reviewed.value = true; state.reason.value = 'Accord A'
    const wait = deferred(); mocks.fetch.mockReturnValueOnce(wait.promise)
    const pending = state.send('CONFIRMED')
    props.received = received(other ? 2 : 1); props.contextRevision = 4
    await nextTick(); wait.resolve(response({ ...received(), changed: true })); await pending
    expect(emit).not.toHaveBeenCalled(); expect(state.reason.value).toBe(''); expect(state.error.value).toBe('')
  })

  it('conserve le refus serveur sans afficher un accord fictif', async () => {
    const props = reactive({ received: received(), contextRevision: 3 })
    await mount(props); state.opened.value = true; state.reviewed.value = true; state.reason.value = 'Accord examiné'
    mocks.fetch.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Relation suspendue' }) })
    await state.send('CONFIRMED')
    expect(state.error.value).toBe('Relation suspendue'); expect(emit).not.toHaveBeenCalled()
    expect(state.opened.value).toBe(true)
  })

  it('ne restaure pas les termes d’une ancienne ouverture après fermeture et réouverture', async () => {
    const props = reactive({ rfq: { id: 1, selected_quote_id: 2, quotes: [{ id: 2, origin: 'NETWORK' }] } })
    await mount(props)
    const old = deferred(); mocks.fetch.mockReturnValueOnce(old.promise)
    const pending = state.open(); state.opened.value = false
    mocks.fetch.mockResolvedValueOnce(response({ terms_version: 2 })); await state.open()
    old.resolve(response({ terms_version: 1 })); await pending
    expect(state.terms.value.terms_version).toBe(2)
  })

  it('un accusé livré conserve le statut de demande en attente de décision bancaire', async () => {
    const rfq = { id: 1, electronic_execution: { state: 'PENDING', execution_reference: 'EXE-TEST',
      transport: { state: 'DELIVERED', attempts: 2, history: [] } } }
    const rendered = createSSRApp({ render: () => h(Panel, { rfq }) }); rendered.use(createPinia())
    const html = await renderToString(rendered)
    expect(html).toContain('confirmation bancaire attendue'); expect(html).toContain('Réception confirmée')
    expect(html).not.toContain('Exécution confirmée électroniquement')
    expect(html).not.toContain('Envoyer la demande électronique')
  })
})
