import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, h, nextTick, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { recordMarketReference, marketProvenanceFields } from '../utils/marketProvenance.js'
import { rfqBasketFromParams, rfqUnderlyingToParams } from '../utils/rfqBasket.js'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import RfqView from './RfqView.vue'
import AdminMarketDataView from './AdminMarketDataView.vue'
import ComparatorTab from '../components/ComparatorTab.vue'
import MarketDataProvenance from '../components/MarketDataProvenance.vue'

const reply=(data,status=200)=>({ok:status>=200 && status<300,status,json:async()=>data})
const flush=async()=>{for(let i=0;i<18;i++)await nextTick()}
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r});return {promise,resolve}}
const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
let app,state,pinia
beforeEach(()=>{
  pinia=createPinia();setActivePinia(pinia);localStorage.clear()
  vi.stubGlobal('window',{addEventListener(){},removeEventListener(){}})
  vi.stubGlobal('document',{addEventListener(){},removeEventListener(){},visibilityState:'visible'})
  vi.stubGlobal('fetch',vi.fn(async url=>reply(String(url).includes('/api/parse')?{ok:true,params:[],constats:[]}:[])))
})
afterEach(()=>{app?.unmount();app=null;vi.unstubAllGlobals()})
async function mount(Component){
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/test',component:{render:()=>null}}]})
  await router.push('/test');await router.isReady()
  app=renderer.createApp({setup(_,ctx){state=Component.setup({},ctx);return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.use(pinia);app.use(router);app.mount({});await flush();return state
}
const market=q=>({vols:{A:.23456789},div_yields:q==null?{}:{A:q},n_obs:252,
  requested_asof:'2026-08-27',effective_dates:{A:'2026-08-27'},provider:'YAHOO_FINANCE',
  dividend_profiles:{A:q==null?{ok:false,error:'feed absent'}:{ok:true,yield_declared:q,asof_effective:'2026-08-27'}},
  estimator:{volatility:'RMS_LOG_RETURNS'},corr:{A:{A:1}},tickers:['A']})

it('référence, surcharge et valeur exacte survivent au panier RFQ',()=>{
  const row={ticker:'A',sigma:23.456789,q:1}
  recordMarketReference(row,market(.01),'A');row.q=2.00123
  const saved=rfqUnderlyingToParams(row),reopened=rfqBasketFromParams([saved])[0]
  expect(saved.market_data.references.q.value).toBe(.01)
  expect(saved.market_data.overrides.q).toBe(.0200123)
  expect(reopened.q).toBe(2.00123)
  expect(rfqUnderlyingToParams(reopened).market_data).toEqual(saved.market_data)
})
it('les métadonnées sont copiées et les anciennes références ne deviennent pas celles du nouveau ticker',()=>{
  const row={ticker:'A',sigma:23.456789,q:1},data=market(.01)
  recordMarketReference(row,data,'A');data.dividend_profiles.A.yield_declared=99
  row.ticker='B'
  expect(marketProvenanceFields(row).market_data.references.q.value).toBe(.01)
  expect(marketProvenanceFields(row).market_data.overrides.q).toBe(.01)
})
it('un profil en erreur interdit un zéro de repli, et conserve l’hypothèse explicite',()=>{
  const row={ticker:'A',sigma:23.456789,q:2},data=market(null)
  data.div_yields.A=0;recordMarketReference(row,data,'A')
  expect(row.q).toBe(2);expect(row.market_data.references.q).toBeUndefined()
  expect(row.market_data.unavailable.q.error).toBe('feed absent')
})
it.each(['one','all'])('le Pricer %s transmet la source puis conserve la surcharge dans le corps moteur',async mode=>{
  const store=usePricingStore();store.underlyings[0].ticker='A'
  fetch.mockResolvedValue(reply(market(.01)))
  await (mode==='one'?store.loadYfOne(0):store.loadYfAll())
  store.underlyings[0].q=2.00123
  const used=store.draftProductBody().underlyings[0]
  expect(used.q).toBe(.0200123)
  expect(used.market_data.references.q.value).toBe(.01)
  expect(used.market_data.effective.sigma).toBe(used.sigma)
  expect(used.market_data.overrides.q).toBe(used.q)
})
it.each([null,0])('le chargement RFQ distingue dividende manquant et zéro sourcé : %s',async q=>{
  await mount(RfqView);const row=state.createBasket[0];row.ticker='A';row.q=2
  state.form.pricing_date='2026-08-27';fetch.mockResolvedValue(reply(market(q)))
  await state.loadCreateUnderlyingParams()
  expect(fetch.mock.calls.at(-1)[0]).toContain('asof=2026-08-27')
  expect(row.q).toBe(q==null?2:0);expect(row.sigma).toBe(23.456789)
  expect(state.createYfStatus.value).toContain(q==null?'inconnu':'✓')
})
it.each(['override','date','replacement','round_trip'])('une réponse RFQ tardive ne remplace pas le contexte changé : %s',async change=>{
  await mount(RfqView);const row=state.createBasket[0],wait=deferred();row.ticker='A';row.q=2
  fetch.mockReturnValueOnce(wait.promise);const pending=state.loadCreateUnderlyingParams()
  if(change==='override')row.q=4
  if(change==='date')state.form.pricing_date='2027-01-01'
  if(change==='replacement')state.createBasket[0]={...row,ticker:'B'}
  if(change==='round_trip'){row.ticker='B';row.ticker='A'}
  const before=JSON.stringify(state.createBasket)
  wait.resolve(reply(market(.01)));await pending
  expect(JSON.stringify(state.createBasket)).toBe(before);expect(state.createYfLoading.value).toBe(false)
})
it.each([null,0])('le comparateur refuse les données inconnues et accepte le vrai zéro : %s',async q=>{
  const store=usePricingStore();vi.spyOn(store,'ensureScriptValidated').mockResolvedValue(true)
  await mount(ComparatorTab)
  fetch.mockImplementation(async url=>reply(String(url).includes('hist_vol')?market(q):{price:.98}))
  const row={tickers:['A'],corr_matrix:[[1]]};await state.quotePrice(row)
  const price=fetch.mock.calls.find(([url])=>url==='/api/price')
  if(q==null){expect(price).toBeUndefined();expect(state.rowState(row).error).toContain('inconnu')}
  else {expect(JSON.parse(price[1].body).underlyings[0]).toMatchObject({q:0,market_data:{references:{q:{value:0}}}})}
})
it('un fetch administratif réussi mais non qualifié ne devient pas OK',async()=>{
  await mount(AdminMarketDataView)
  fetch.mockResolvedValue(reply({available:true,consumer_available:false,cache_status:'unqualified',bases:{unadjusted:{status:'MISSING'}}}))
  const item={key:'A',ticker:'A'};await state.fetchOne(item)
  expect(item.cache_status).toBe('unqualified');expect(item.bases.unadjusted.status).toBe('MISSING')
})
it.each([false,true])('les références et surcharges respectent le mode démo : %s',async demo=>{
  const row={ticker:'CONFIDENTIAL',sigma:23.456789,q:1};recordMarketReference(row,market(.01),'A');row.q=2.00123
  useDemoModeStore().enabled=demo
  const html=await renderToString(createSSRApp({render:()=>h(MarketDataProvenance,{row})}).use(pinia))
  if(demo){expect(html).not.toContain('2.00123');expect(html).not.toContain('YAHOO_FINANCE')}
  else {expect(html).toContain('2.00123');expect(html).toContain('surcharge');expect(html).toContain('2026-08-27')}
})
