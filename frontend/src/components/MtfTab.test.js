import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createSSRApp, createRenderer, nextTick, ssrContextKey } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import MtfTab from './MtfTab.vue'
import MtfDrilldownModal from './MtfDrilldownModal.vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'

let pinia, app
beforeEach(() => {
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => { app?.unmount(); app = null; vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('affiche la graine effective 42 en lecture seule', async () => {
  const html = await renderToString(createSSRApp(MtfTab).use(pinia))
  expect(html).toContain('Graine fixe')
  const input = html.match(/<input[^>]*aria-label="Graine Monte Carlo fixe"[^>]*>/)?.[0]
  expect(input).toBeTruthy()
  expect(input).toContain('value="42"')
  expect(input).toContain('readonly')
})

it('conserve le masquage de la graine en mode démo', async () => {
  useDemoModeStore().enabled = true
  const html = await renderToString(createSSRApp(MtfTab).use(pinia))
  expect(html).not.toContain('aria-label="Graine Monte Carlo fixe"')
  expect(html).toContain('Graine fixe')
  expect(html).toContain('sv-input-mask')
})

it.each(['heston','sabr','localvol'])('permet de lancer le MTF en %s',async model=>{
  const store=usePricingStore()
  store.result={price:.97};store.globalParams.model=model
  const html=await renderToString(createSSRApp(MtfTab).use(pinia))
  expect(html).toContain('Même modèle que le Pricer')
  expect(html).not.toMatch(/<button[^>]*btn-primary[^>]*disabled/)
})

it('demande une qualification du levier avant de sélectionner LSV', async () => {
  const store = usePricingStore()
  store.result = { price: .97 }
  store.globalParams.model = 'lsv'
  const html = await renderToString(createSSRApp(MtfTab).use(pinia))
  expect(html).toContain('Le levier LSV doit être qualifié')
  expect(html).toMatch(/<button[^>]*disabled[^>]*>[\s\S]*?Lancer/)
  expect(store.globalParams.model).toBe('lsv')
})

it('demande de repricer avant le MTF quand le prix de référence est périmé',async()=>{
  const store=usePricingStore()
  store.script='AT MATURITY:\n  PAY 1';store.globalParams.T=1
  vi.stubGlobal('fetch',vi.fn(async url=>({ok:true,json:async()=>String(url).endsWith('/api/parse')
    ? {ok:true,params:[],constats:[],has_maturity_event:true} : {price:.97}})))
  await store.runPricing()
  store.globalParams.r+=1
  await store.runMtf()
  expect(store.error).toContain('prix de référence est périmé')
  expect(fetch.mock.calls.some(([url])=>url==='/api/mtf')).toBe(false)
})

it('envoie et conserve la graine effective pour l’éventail et son drill-down', async () => {
  const store = usePricingStore()
  store.script = 'AT MATURITY:\n  PAY 1'
  store.globalParams.T = 1
  store.globalParams.seed = 101
  store.result = { price: 1 }
  vi.stubGlobal('fetch', vi.fn(async url => ({
    ok: true,
    json: async () => String(url).endsWith('/api/parse')
      ? { ok: true, params: [], constats: [], has_maturity_event: true }
      : { results: [], mtm_dates: [.25, .5], context_fingerprint: 'a'.repeat(64) },
  })))
  await store.runMtf({ seed: 202, n_outer: 20, n_inner: 50, n_dates: 2 })
  const call = fetch.mock.calls.find(([url]) => url === '/api/mtf')
  expect(call).toBeTruthy()
  const body = JSON.parse(call[1].body)
  expect(body).toMatchObject({ seed: 42, n_outer: 20, n_inner: 50, n_dates: 2 })
  await store.runMtfDrilldown({ t: .5, ids: [0] })
  const detail = fetch.mock.calls.find(([url]) => url === '/api/mtf/drilldown')
  expect(detail).toBeTruthy()
  expect(JSON.parse(detail[1].body)).toMatchObject({ seed: 42, t: .5, scenario_ids: [0],
    mtm_dates: [.25, .5], context_fingerprint: 'a'.repeat(64) })
})

it('compare deux modèles et rejoue le P₀ et l’empreinte du modèle sélectionné', async () => {
  const store = usePricingStore()
  store.script = 'AT MATURITY:\n  PAY 1'
  store.globalParams.T = 1
  store.result = { price: 1 }
  const a = { model: 'constant', main_price: 94, results: [], mtm_dates: [.5], context_fingerprint: 'a'.repeat(64) }
  const b = { ...a, model: 'heston', main_price: 92, context_fingerprint: 'b'.repeat(64) }
  vi.stubGlobal('fetch', vi.fn(async url => ({ ok: true, json: async () => {
    if (url === '/api/parse') return { ok: true, params: [], constats: [], has_maturity_event: true }
    if (url === '/api/mtf/compare') return { a: { model: 'constant', result: a }, b: { model: 'heston', result: b } }
    return { model: 'heston', scenarios: [] }
  } })))
  await store.runMtf({ model: 'constant', modelB: 'heston' })
  expect(store.error).toBeNull()
  const request = JSON.parse(fetch.mock.calls.find(([url]) => url === '/api/mtf/compare')[1].body)
  expect(request.a).toMatchObject({ model: 'constant', reference_paths: 20000 })
  expect(request.b).toMatchObject({ ...request.a, model: 'heston' })
  expect(store.mtf.main_price).toBe(94)
  store.selectMtfLeg('b')
  await store.runMtfDrilldown({ t: .5, ids: [0] })
  const detail = JSON.parse(fetch.mock.calls.find(([url]) => url === '/api/mtf/drilldown')[1].body)
  expect(detail).toMatchObject({ model: 'heston', main_price: 92, context_fingerprint: 'b'.repeat(64) })
  expect(store.globalParams.model).toBe('constant')
  store.globalParams.r++
  expect(store.mtfIsStale).toBe(true)
})

it('ignore une réponse A/B tardive après modification du marché', async () => {
  const store = usePricingStore()
  store.script = 'AT MATURITY:\n  PAY 1'
  store.globalParams.T = 1
  store.result = { price: 1 }
  let respond, started
  const pending = new Promise(resolve => { respond = resolve })
  const sent = new Promise(resolve => { started = resolve })
  vi.stubGlobal('fetch', vi.fn(async url => {
    if (url === '/api/parse') return { ok: true, json: async () => ({ ok: true, params: [], constats: [], has_maturity_event: true }) }
    started()
    return pending
  }))
  const run = store.runMtf({ model: 'constant', modelB: 'sabr' })
  await sent
  store.globalParams.r++
  respond({ ok: true, json: async () => ({ a: { result: { main_price: 100 } }, b: { error: 'SABR indisponible' } }) })
  await run
  expect(store.mtfComparison).toBeNull()
  expect(store.mtfLoading).toBe(false)
})

it('change les statistiques, quantiles et histogrammes avec la population, en gardant les créances impayées', async () => {
  const store = usePricingStore()
  const all = {mean: 158/3, p05: 0}, outstanding = {mean: 79, p05: 50}
  store.mtf = {main_price: 100, results: [{t: .5, pvs: [0,108,50], alive: [false,false,true],
    outstanding: [false,true,true], pending_settlement: [false,true,false],
    n_outer: 3, n_settled: 1, n_outstanding: 2, stats_all: all, stats_outstanding: outstanding,
    thin_all: false, thin_outstanding: false}]}
  const run = vi.spyOn(store, 'runMtfDrilldown').mockResolvedValue({})
  const renderer = createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
  let state
  app = renderer.createApp({setup(){state=MtfTab.setup({}, {expose(){}});return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()}); app.use(pinia); app.mount({})
  expect(state.displayRows.value[0].stats).toMatchObject(all)
  expect(state.histData.value.buckets.flat().sort()).toEqual([0,1,2])
  state.openQuantiles(state.displayRows.value[0])
  expect(run.mock.calls[0][0].ids).toContain(0)
  state.distributionView.value = 'outstanding'
  await nextTick()
  expect(state.displayRows.value[0].stats).toMatchObject(outstanding)
  expect(state.displayRows.value[0].n_selected).toBe(2)
  expect(state.histData.value.buckets.flat().sort()).toEqual([1,2])
  state.openQuantiles(state.displayRows.value[0])
  expect(run.mock.calls[1][0].ids.sort()).toEqual([1,2])
})

it('affiche une créance impayée après arrêt du payoff avec constatation et paiement distincts', async () => {
  const context = {}
  const scenario = {id:0,alive:false,outstanding:true,status:'PENDING_SETTLEMENT',mtf:107.97,pending_pv:107.97,
    wof_t0:null,spots_t0:[],future_flows:[{observation_t:30/365.25,t_abs:35/365.25,t:3/365.25,
      status:'ACQUIRED_UNPAID',lbl:'Remboursement',proba:100,amount_if_fires:108,e_amount:108,df:.9997,pv:107.97}],
    sum_pv:107.97,pv_residual:0,realized_cash:8,realized_flows:[],path:{t:[],wof:[],assets:[[]]},observations:[],
    final:{recalled:true,stop_t:30/365.25,total_undiscounted:116,pv_at_0:115,flows:[]}}
  const html = await renderToString(createSSRApp(MtfDrilldownModal, {modelValue:true,
    drill:{origin_date:'2026-01-01',t:32/365.25,n_inner:50,n_outer:100,step_k:0,n_assets:1,
      asset_names:['Test'],barriers:[],scenarios:[scenario]}}).use(pinia), context)
  const content = html + Object.values(context.teleports || {}).join('')
  expect(content).toContain('Créance acquise impayée')
  expect(content).toContain('31/01/2026'); expect(content).toContain('05/02/2026')
  expect(content).not.toContain('le mark est nul par construction')
})

it('affiche dès réception la même première date qu’après réouverture, sans masquer les zéros finaux', async () => {
  const store = usePricingStore()
  const renderer = createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
  let state
  app = renderer.createApp({setup(){state=MtfTab.setup({}, {expose(){}});return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()}); app.use(pinia); app.mount({})
  const row = (t, value) => ({t, pvs:[value,value], alive:[value>0,value>0],
    outstanding:[value>0,value>0], n_outer:2, stats_all:{mean:value,e_mtm:value},
    stats_outstanding:value?{mean:value,e_mtm:value}:null,thin_all:false,thin_outstanding:!value})
  store.mtf = {main_price:89.02,results:[row(.5,91.5),row(3.02,0)]}
  await nextTick()
  expect(state.tileRow.value.t).toBe(.5)
  expect(state.tileRow.value.stats.mean).toBe(91.5)
  expect(state.histData.value.lo).toBe(91.5)
  state.tileDateIdx.value = 1
  await nextTick()
  expect(state.tileRow.value.stats.mean).toBe(0)
  state.distributionView.value = 'outstanding'
  await nextTick()
  expect(state.tileRow.value.t).toBe(.5)
  store.mtf = {main_price:89.02,results:[row(.75,93),row(3.02,0)]}
  await nextTick()
  expect(state.tileRow.value.t).toBe(.75)
})
