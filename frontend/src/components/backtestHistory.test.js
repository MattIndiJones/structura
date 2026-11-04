import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, h, nextTick, reactive, ref, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import { useBacktestHistory } from '../composables/useBacktestHistory.js'
import { usePricingStore } from '../stores/pricing.js'
import BacktestTab from './BacktestTab.vue'
import BacktestHistoryDetails from './BacktestHistoryDetails.vue'
import ComparatorTab from './ComparatorTab.vue'

const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
const reply = (body, ok = true) => ({ ok, json: async () => body })
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const flush = async () => { for (let i = 0; i < 12; i++) await nextTick() }
const bounds = start => ({ available: true, local_only: true, start_effective: start, end_effective: '2024-01-31' })
let app, state
beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })
afterEach(() => { app?.unmount(); app = null; vi.unstubAllGlobals(); vi.restoreAllMocks() })
async function mount(setup) {
  app = renderer.createApp({ setup() { state = setup(); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.mount({}); await flush()
  return state
}

it('préremplit le début commun local et actualise le panier, sans lancer de backtest', async () => {
  const store = reactive({ underlyings: [{ ticker: ' a ' }], backtest: null })
  const form = ref({ start_date: '', end_date: '2024-01-31' })
  vi.stubGlobal('fetch', vi.fn(async url => reply(bounds(String(url).includes('A%2CB') ? '2024-01-08' : '2024-01-02'))))
  await mount(() => useBacktestHistory(store, form))
  expect(form.value.start_date).toBe('2024-01-02')
  store.underlyings.push({ ticker: 'B' }); await flush()
  expect(form.value.start_date).toBe('2024-01-08')
  expect(fetch.mock.calls.every(([url]) => String(url).startsWith('/api/backtest/history-bounds?'))).toBe(true)
})

it('conserve une saisie manuelle pendant la recherche et permet de revenir au début commun', async () => {
  const wait = deferred(), form = ref({ start_date: '', end_date: '2024-01-31' })
  vi.stubGlobal('fetch', () => wait.promise)
  await mount(() => useBacktestHistory(reactive({ underlyings: [{ ticker: 'A' }] }), form))
  state.manualStart.value = true; form.value.start_date = '2024-01-10'
  wait.resolve(reply(bounds('2024-01-02'))); await flush()
  expect(form.value.start_date).toBe('2024-01-10')
  state.useSuggestedStart()
  expect(form.value.start_date).toBe('2024-01-02')
  expect(state.manualStart.value).toBe(false)
})

it('ignore la réponse tardive du panier précédent', async () => {
  const wait = deferred(), store = reactive({ underlyings: [{ ticker: 'A' }] })
  const form = ref({ start_date: '', end_date: '2024-01-31' })
  vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(wait.promise).mockResolvedValue(reply(bounds('2024-01-08'))))
  await mount(() => useBacktestHistory(store, form))
  store.underlyings[0].ticker = 'B'; await flush()
  wait.resolve(reply(bounds('2024-01-02'))); await flush()
  expect(form.value.start_date).toBe('2024-01-08')
  expect(state.loading.value).toBe(false)
})

it('laisse le début automatique vide sans historique local puis retient la date chargée au lancement', async () => {
  const store = reactive({ underlyings: [{ ticker: 'A' }], backtest: null })
  const form = ref({ start_date: '', end_date: '2024-01-31' })
  vi.stubGlobal('fetch', async () => reply({ available: false, local_only: true }))
  await mount(() => useBacktestHistory(store, form))
  expect(form.value.start_date).toBe('')
  store.backtest = { history_policy: { effective_start: '2024-01-08' } }; await flush()
  expect(form.value.start_date).toBe('2024-01-08')
})

it('une panne de prévisualisation reste visible et ne remplace pas le début par une date inventée', async () => {
  const form = ref({ start_date: '', end_date: '2024-01-31' })
  vi.stubGlobal('fetch', async () => reply({ detail: 'Historique indisponible' }, false))
  await mount(() => useBacktestHistory(reactive({ underlyings: [{ ticker: 'A' }] }), form))
  expect(state.error.value).toContain('Historique indisponible')
  expect(form.value.start_date).toBe('')
  expect(state.loading.value).toBe(false)
})

it('le formulaire propose Following avec dix jours et exige tous les tickers du panier', async () => {
  const store = usePricingStore(); store.underlyings[0].ticker = 'A'
  vi.stubGlobal('fetch', async () => reply(bounds('2024-01-02')))
  await mount(() => BacktestTab.setup({}, { expose() {} }))
  expect(state.form.value).toMatchObject({ start_date: '2024-01-02', history_mode: 'following', max_delay_days: 10 })
  expect(state.canRun.value).toBe(true)
  store.addUnderlying(); await flush()
  expect(state.canRun.value).toBe(false)
})

it.each(['backtest', 'comparator'])('le lancement %s ne transforme pas le cache court en début manuel', async mode => {
  const store = usePricingStore(); store.underlyings[0].ticker = 'A'
  vi.stubGlobal('fetch', async () => reply(bounds('2024-01-02')))
  await mount(() => (mode === 'backtest' ? BacktestTab : ComparatorTab).setup({}, { expose() {} }))
  const run = vi.spyOn(store, mode === 'backtest' ? 'runBacktest' : 'runBacktestCompare').mockResolvedValue({})
  const launch = () => mode === 'backtest' ? state.launchBacktest() : state.launch()
  launch()
  expect(run.mock.calls[0][mode === 'backtest' ? 0 : 1].start_date).toBeNull()
  state.history.manualStart.value = true
  state.form.value.start_date = '2024-01-10'
  launch()
  expect(run.mock.calls[1][mode === 'backtest' ? 0 : 1].start_date).toBe('2024-01-10')
})

it.each([{}, { start_date: '2024-01-10', history_mode: 'strict', max_delay_days: 0, rf_rate: 0 }])(
  'transmet la convention et préserve les choix explicites %j', async params => {
    const store = usePricingStore(); store.script = 'AT MATURITY:\n  PAY 1'; store.underlyings[0].ticker = 'A'
    vi.stubGlobal('fetch', vi.fn(async url => reply(url === '/api/parse' ? { ok: true, params: [], constats: [] } : { rows: [] })))
    await store.runBacktest(params)
    const request = fetch.mock.calls.find(([url]) => url === '/api/backtest')
    expect(request).toBeDefined()
    expect(JSON.parse(request[1].body)).toMatchObject({
      start_date: params.start_date || null, history_mode: params.history_mode || 'following',
      max_delay_days: params.max_delay_days ?? 10, rf_rate: params.rf_rate ?? 2,
    })
    expect(store.loading).toBe(false)
  })

it('un résultat tardif ne remplace pas un panier modifié', async () => {
  const wait = deferred(), store = usePricingStore()
  store.script = 'AT MATURITY:\n  PAY 1'; store.underlyings[0].ticker = 'A'
  vi.stubGlobal('fetch', vi.fn(async url => url === '/api/backtest' ? wait.promise : reply({ ok: true, params: [], constats: [] })))
  const pending = store.runBacktest()
  await vi.waitFor(() => expect(fetch.mock.calls.some(([url]) => url === '/api/backtest')).toBe(true))
  store.underlyings[0].ticker = 'B'; wait.resolve(reply({ rows: [{ date: '2024-01-02' }] })); await pending
  expect(store.backtest).toBeNull()
  expect(store.loading).toBe(false)
})

it('le comparateur propose le début commun des candidats et Following à dix jours', async () => {
  vi.stubGlobal('fetch', vi.fn(async url => reply(String(url).includes('history-bounds') ? bounds('2024-01-08') : [])))
  await mount(() => ComparatorTab.setup({}, { expose() {} }))
  expect(state.form.value.start_date).toBe('')
  state.pool.value = [{ ticker: 'A' }, { ticker: 'B' }]; await flush()
  expect(state.form.value).toMatchObject({ start_date: '2024-01-08', history_mode: 'following', max_delay_days: 10 })
  state.history.manualStart.value = true; state.form.value.start_date = '2024-01-15'
  state.pool.value.push({ ticker: 'C' }); await flush()
  expect(state.form.value.start_date).toBe('2024-01-15')
})

it.each([{}, { start_date: '2024-01-10', history_mode: 'strict', max_delay_days: 0, rf_rate: 0 }])(
  'le comparateur transmet le début automatique, les conventions et la devise %j', async params => {
    const store = usePricingStore(); store.script = 'AT MATURITY:\n  PAY 1'
    store.globalParams.deal_ccy = 'USD'; store.globalParams.payment_date = '2027-01-06'
    vi.stubGlobal('fetch', vi.fn(async url => reply(url === '/api/parse' ? { ok: true, params: [], constats: [] } : { results: [] })))
    await store.runBacktestCompare([{ name: 'A', ticker: 'A' }], params)
    const body = JSON.parse(fetch.mock.calls.find(([url]) => url === '/api/backtest/compare')[1].body)
    expect(body).toMatchObject({ start_date: params.start_date || null, history_mode: params.history_mode || 'following',
      max_delay_days: params.max_delay_days ?? 10, rf_rate: params.rf_rate ?? 2, settlement_ccy: 'USD', payment_date: '2027-01-06' })
  })

it('le comparateur ignore un résultat préparé pour une ancienne sélection de candidats', async () => {
  const wait = deferred(), store = usePricingStore(); let current = true
  store.script = 'AT MATURITY:\n  PAY 1'
  vi.stubGlobal('fetch', vi.fn(async url => url === '/api/backtest/compare' ? wait.promise : reply({ ok: true, params: [], constats: [] })))
  const pending = store.runBacktestCompare([{ name: 'A', ticker: 'A' }], {}, () => current)
  await vi.waitFor(() => expect(fetch.mock.calls.some(([url]) => url === '/api/backtest/compare')).toBe(true))
  current = false; wait.resolve(reply({ results: [{ tickers: ['A'] }] })); await pending
  expect(store.comparator).toBeNull(); expect(store.comparatorLoading).toBe(false)
})

const result = () => ({ rows: [{ date: '2024-01-02', irr: .1 }], history_policy: {
  mode: 'following', max_delay_days: 10, effective_start: '2024-01-02', effective_end: '2024-01-31',
  adjusted_underlyings: ['A', 'B'], disclaimer: 'Historique ajusté : aucun cours futur antidaté.',
  adjustments: Array.from({ length: 51 }, (_, i) => ({ ticker: i === 50 ? 'B' : 'A', window_start: '2024-01-02',
    requested_date: '2024-01-03', effective_date: '2024-01-04', delay_days: 1,
    reason: i === 50 ? 'COMMON_BASKET_DATE' : 'MISSING_QUOTE' })),
} })

it('affiche le disclaimer hors du menu repliable et pagine les ajustements', async () => {
  const ssr = createSSRApp({ render: () => h(BacktestHistoryDetails, { result: result() }) }); ssr.use(createPinia())
  const html = await renderToString(ssr)
  expect(html.indexOf('role="alert"')).toBeLessThan(html.indexOf('<details>'))
  expect(html).toContain('51 ajustement(s)')
  expect(html).toContain('Page 1 / 2')
  expect(html).toContain('03/01/2024'); expect(html).toContain('04/01/2024')
  expect(html.match(/Cours absent/g)).toHaveLength(50)
})

it('exporte toutes les dates et la méthode même quand le panneau est paginé', async () => {
  const data = result(), anchor = { click: vi.fn() }; let blob
  vi.stubGlobal('document', { createElement: () => anchor })
  vi.spyOn(URL, 'createObjectURL').mockImplementation(value => { blob = value; return 'blob:test' })
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  await mount(() => BacktestHistoryDetails.setup({ result: data }, { expose() {} }))
  state.exportResult()
  expect(JSON.parse(await blob.text())).toEqual(data)
  expect(anchor.download).toBe('structura-backtest.json'); expect(anchor.click).toHaveBeenCalledOnce()
  state.page.value = 1
  expect(state.visibleRows.value).toEqual([data.history_policy.adjustments[50]])
})
