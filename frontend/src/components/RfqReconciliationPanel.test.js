import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, nextTick, reactive, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import Panel from './RfqReconciliationPanel.vue'

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), durable: vi.fn() }))
vi.mock('../utils/api.js', () => ({ apiFetch: (...args) => mocks.fetch(...args), apiErrorMessage: data => data.detail }))
vi.mock('../utils/commands.js', () => ({ durableCommand: (...args) => mocks.durable(...args) }))
const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
const response = (data, ok = true) => ({ ok, json: async () => data })
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const entry = id => ({ id, reconciliation: { state: 'PEER_UNKNOWN', differences: [] } })
let app, state
async function mount(props) {
  app = renderer.createApp({ setup(_, ctx) { state = Panel.setup(props, ctx); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.mount({}); await nextTick()
}
beforeEach(() => { setActivePinia(createPinia()); mocks.fetch.mockReset(); mocks.durable.mockReset(); mocks.durable.mockImplementation((op, payload, send) => send('resume-command-fixed-key')) })
afterEach(() => app?.unmount())

it('la consultation seule ne peut pas relancer des échanges', async () => {
  const props = reactive({ entry: entry('a'), canResume: false, contextRevision: 1 }); await mount(props)
  await state.refresh(true); expect(mocks.fetch).not.toHaveBeenCalled()
  mocks.fetch.mockResolvedValueOnce(response({ state: 'PEER_UNKNOWN' })); await state.refresh()
  expect(mocks.fetch).toHaveBeenCalledWith('/api/rfq-reconciliation/a')
})
it('utilise une commande durable et n’envoie aucun calcul privé', async () => {
  const props = reactive({ entry: entry('a'), canResume: true, contextRevision: 1 }); await mount(props)
  mocks.fetch.mockResolvedValueOnce(response({ state: 'LOCAL_BOOKING_MISSING' })); await state.refresh(true)
  expect(mocks.durable).toHaveBeenCalledWith('rfq-reconcile', { execution_id: 'a' }, expect.any(Function))
  expect(JSON.parse(mocks.fetch.mock.calls[0][1].body)).toEqual({ command_key: 'resume-command-fixed-key' })
  expect(state.state.value.state).toBe('LOCAL_BOOKING_MISSING')
})
it.each([false, true])('ignore une réponse tardive après réouverture ou autre exécution, autre=%s', async other => {
  const props = reactive({ entry: entry('a'), canResume: true, contextRevision: 1 }); await mount(props)
  const wait = deferred(); mocks.fetch.mockReturnValueOnce(wait.promise); const pending = state.refresh(true)
  props.entry = entry(other ? 'b' : 'a'); props.contextRevision = 2; await nextTick()
  wait.resolve(response({ state: 'MATCHED' })); await pending
  expect(state.state.value.state).toBe('PEER_UNKNOWN')
})
it('un refus serveur ne devient pas une concordance', async () => {
  const props = reactive({ entry: entry('a'), canResume: true, contextRevision: 1 }); await mount(props)
  mocks.fetch.mockResolvedValueOnce(response({ detail: 'Droit révoqué' }, false)); await state.refresh(true)
  expect(state.error.value).toBe('Droit révoqué'); expect(state.state.value.state).toBe('PEER_UNKNOWN')
})
it('accepte la réponse en cours si une actualisation conserve la même identité', async () => {
  const props = reactive({ entry: entry('a'), canResume: true, contextRevision: 1 }); await mount(props)
  const wait = deferred(); mocks.fetch.mockReturnValueOnce(wait.promise); const pending = state.refresh(true)
  props.entry = entry('a'); await nextTick(); wait.resolve(response({ state: 'MATCHED' })); await pending
  expect(state.state.value.state).toBe('MATCHED')
})
it('affiche les écarts et la date distante sans déclarer les livres rapprochés', async () => {
  const html = await renderToString(createSSRApp(Panel, { entry: { id: 'a', reconciliation: {
    state: 'MISMATCH', peer_version: 2, peer_received_at: '2026-10-24T10:00:00Z',
    peer: { observed_at: '2026-10-24T09:59:00Z' },
    differences: [{ side: 'PEER', field: 'price', expected: 98.5, actual: 99 }],
  } }, canResume: false }))
  expect(html).toContain('Écart à examiner'); expect(html).toContain('Prix (%)'); expect(html).toContain('État distant v2')
  expect(html).toContain('98,50'); expect(html).toContain('99,00')
  expect(html).not.toContain('Exécution et bookings rapprochés'); expect(html).not.toContain('Rapprocher et reprendre les échanges')
})
