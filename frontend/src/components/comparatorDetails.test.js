import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, h, nextTick, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import ComparatorTab from './ComparatorTab.vue'
import BacktestResults from './BacktestResults.vue'
import { usePricingStore } from '../stores/pricing.js'
import { clearUnderlyings } from '../data/commonUnderlyings.js'

const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
const reply = (body, ok = true) => ({ ok, json: async () => body })
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const flush = async () => { for (let i = 0; i < 12; i++) await nextTick() }
const row = ticker => ({ tickers: [ticker], names: [ticker === 'CS.PA' ? 'AXA' : 'BNP Paribas'],
  corr_matrix: [[1]], median_irr: .1, mean_irr: .08, p10_irr: -.1, worst_irr: -.2,
  pct_positive: 95, early_recall_pct: 80, n_windows: 2 })
const comparison = () => ({ results: [row('CS.PA'), row('BNP.PA')], comparison_context: {
  request: { script: 'original comparison', start_date: '2015-01-02', end_date: '2026-10-30', history_mode: 'following', max_delay_days: 10 },
  history_hash: 'a'.repeat(64),
} })
const detail = ticker => ({ selected_tickers: [ticker], rows: [
  { date: '2024-01-02', irr: .1, T_actual: 1, early_recall: true },
  { date: '2024-02-02', irr: -.1, T_actual: 3, early_recall: false },
], n_windows: 2, mean_irr: 0, median_irr: .1, p10: -.1, p90: .1, pct_positive: 50, overlap_pct: 90, sharpe: .3 })
const market = { vols: { 'CS.PA': .234567 }, div_yields: { 'CS.PA': .02123 },
  dividend_profiles: { 'CS.PA': { ok: true, yield_declared: .02123 } }, corr: { 'CS.PA': { 'CS.PA': 1 } },
  requested_asof: '2026-11-01', price_type: 'ADJUSTED_CLOSE', estimator: { volatility: 'RMS_LOG_RETURNS' } }
let app, state, store
beforeEach(() => {
  setActivePinia(createPinia()); localStorage.clear(); clearUnderlyings()
  store = usePricingStore(); store.script = 'AT MATURITY:\n  PAY 1'; store.comparator = comparison()
  vi.spyOn(store, 'ensureScriptValidated').mockResolvedValue(true)
  vi.stubGlobal('fetch', vi.fn(async url => {
    if (String(url).includes('/underlyings')) return reply([{ group: 'Tests', items: [{ ticker: 'CS.PA', label: 'AXA', ccy: 'EUR' }] }])
    if (String(url).includes('/hist_vol')) return reply(market)
    if (url === '/api/price') return reply({ price: .9876 })
    if (url === '/api/backtest/compare/detail') return reply(detail('CS.PA'))
    return reply({ ok: true, params: [], constats: [] })
  }))
})
afterEach(() => { app?.unmount(); app = null; clearUnderlyings(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
async function mount() {
  app = renderer.createApp({ setup(_, ctx) { state = ComparatorTab.setup({}, ctx); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.mount({}); await flush()
}

it('charge les fenêtres avec le contexte exact du classement sans modifier le BT général', async () => {
  store.backtest = { marker: 'general-backtest' }; await mount()
  state.form.value.start_date = '2020-01-01'
  await state.selectResult(store.comparator.results[0])
  const body = JSON.parse(fetch.mock.calls.find(([url]) => url === '/api/backtest/compare/detail')[1].body)
  expect(body).toMatchObject({ comparison: { start_date: '2015-01-02' }, tickers: ['CS.PA'], history_hash: 'a'.repeat(64) })
  expect(state.selectedDetail.value.rows).toHaveLength(2)
  expect(store.backtest).toEqual({ marker: 'general-backtest' })
  await state.selectResult(store.comparator.results[0])
  expect(fetch.mock.calls.filter(([url]) => url === '/api/backtest/compare/detail')).toHaveLength(1)
})

it('ignore une réponse tardive après sélection d’un autre titre', async () => {
  const first = deferred(), second = deferred(); await mount()
  fetch.mockImplementation(url => url === '/api/backtest/compare/detail'
    ? (fetch.mock.calls.filter(([name]) => name === url).length === 1 ? first.promise : second.promise) : reply([]))
  const a = state.selectResult(store.comparator.results[0]); await flush()
  const b = state.selectResult(store.comparator.results[1]); await flush()
  second.resolve(reply(detail('BNP.PA'))); await b
  first.resolve(reply(detail('CS.PA'))); await a
  expect(state.selectedDetail.value.selected_tickers).toEqual(['BNP.PA'])
  expect(state.detailLoading.value).toBe(false)
})

it('efface la sélection et le cache lors d’un nouveau classement', async () => {
  await mount(); await state.selectResult(store.comparator.results[0])
  store.comparator = comparison(); await flush()
  expect(state.selectedDetail.value).toBeNull(); expect(state.selectedRow.value).toBeNull()
})

it('affiche le refus de replay si les données ont changé', async () => {
  await mount(); fetch.mockResolvedValueOnce(reply({ detail: 'L’historique a changé. Relancez la comparaison.' }, false))
  await state.selectResult(store.comparator.results[0])
  expect(state.detailError.value).toContain('Relancez la comparaison')
  expect(state.selectedDetail.value).toBeNull()
})

it('partage les deux graphiques, les statistiques et le détail des fenêtres du BT général', async () => {
  const pinia = createPinia()
  const html = await renderToString(createSSRApp({ render: () => h(BacktestResults, { result: detail('CS.PA') }) }).use(pinia))
  expect(html).toContain('Distribution des TRI (%)'); expect(html).toContain('TRI par date de départ')
  expect(html.match(/<canvas/g)).toHaveLength(2)
  expect(html).toContain('Détail des 2 fenêtres'); expect(html).toContain('Fenêtres chevauchées à 90%')
})

it('envoie un prix avec les références qualifiées par séance et tout le contexte du produit', async () => {
  store.globalParams.strike_date = '2026-11-02'; store.globalParams.value_date = '2026-11-04'
  store.globalParams.payment_date = '2029-11-07'; store.globalParams.deal_ccy = 'EUR'
  store.yieldCurve.enabled = true; store.fundingCurve.enabled = true
  await mount()
  const before = JSON.parse(JSON.stringify(store.pricingBody()))
  await state.quotePrice(store.comparator.results[0])
  expect(fetch.mock.calls.some(([url]) => String(url).includes('session_aware=true'))).toBe(true)
  const priceCall = fetch.mock.calls.find(([url]) => url === '/api/price')
  expect(priceCall).toBeDefined()
  const body = JSON.parse(priceCall[1].body)
  for (const key of ['strike_date','value_date','payment_date','settlement_ccy','yield_curve','funding_curve','funding_spread','barrier_monitoring'])
    expect(body[key]).toEqual(before[key])
  expect(body.underlyings[0]).toMatchObject({ ticker: 'CS.PA', ccy: 'EUR', sigma: .234567, q: .02123 })
  expect(body.underlyings[0].market_data.references.sigma.method).toBe('RMS_LOG_RETURNS')
  expect(state.rowState(store.comparator.results[0]).price).toBe(.9876)
  expect(state.rowState(store.comparator.results[0]).assumptions).toEqual([{ ticker: 'CS.PA', sigma: .234567, q: .02123 }])
})

it('ne fabrique pas de prix si la séance ou le dividende requis manque', async () => {
  await mount(); fetch.mockResolvedValueOnce(reply({ error: 'CS.PA : clôture manquante sur une séance ouverte.' }))
  await state.quotePrice(store.comparator.results[0])
  expect(state.rowState(store.comparator.results[0]).error).toContain('séance ouverte')
  expect(fetch.mock.calls.some(([url]) => url === '/api/price')).toBe(false)
})

it('ne transfère pas la calibration Heston du titre initial au candidat', async () => {
  store.globalParams.model = 'heston'; await mount()
  await state.quotePrice(store.comparator.results[0])
  expect(state.rowState(store.comparator.results[0]).error).toContain('adoptez le panier')
  expect(fetch.mock.calls.some(([url]) => url === '/api/price')).toBe(false)
})

it('ignore un prix reçu après modification des paramètres', async () => {
  const wait = deferred(); await mount()
  fetch.mockImplementation(url => url === '/api/price' ? wait.promise : reply(market))
  const pending = state.quotePrice(store.comparator.results[0])
  await vi.waitFor(() => expect(fetch.mock.calls.some(([url]) => url === '/api/price')).toBe(true))
  store.globalParams.r = 4; wait.resolve(reply({ price: .99 })); await pending
  expect(state.rowState(store.comparator.results[0]).price).toBeNull()
})
