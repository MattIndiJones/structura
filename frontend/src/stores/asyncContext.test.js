import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { effectScope, reactive, nextTick } from 'vue'
import { usePricingStore } from './pricing.js'
import { useRfqStore } from './rfq.js'
import { useObservationPreview } from '../composables/useObservationPreview.js'
import { calibrateUnderlying } from '../utils/smileCalibration.js'
import { makeSurface } from '../utils/volSurface.js'

const reply=(data,status=200)=>({ok:status>=200 && status<300,status,json:async()=>data})
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r});return {promise,resolve}}
const flush=async()=>{for(let i=0;i<12;i++) await nextTick()}
let scope
beforeEach(()=>{setActivePinia(createPinia());localStorage.clear()})
afterEach(()=>{scope?.stop();scope=null;vi.unstubAllGlobals()})
const market={vols:{A:.37},tickers:['A'],missing:[],n_obs:252,corr:{A:{A:1}}}
const dividend={ok:true,yield_declared:.01,pays_dividends:false,dividends:[]}

it.each(['one','all'].flatMap(mode=>['ticker','override','replacement','date','correlation','round_trip'].map(change=>[mode,change])))(
  'le chargement %s ignore une réponse après changement %s',async(mode,change)=>{
    const store=usePricingStore(),u=store.underlyings[0],wait=deferred()
    u.ticker='A';u.sigma=20;u.q=2
    vi.stubGlobal('fetch',vi.fn(url=>String(url).includes('hist_vol')?wait.promise:Promise.resolve(reply(dividend))))
    const pending=mode==='one'?store.loadYfOne(0):store.loadYfAll()
    if(change==='ticker')u.ticker='B'
    if(change==='override')u.q=4
    if(change==='replacement')store.underlyings[0]={...u,ticker:'B',sigma:19}
    if(change==='date')store.globalParams.valuation_date='2026-01-02'
    if(change==='correlation')store.corrMatrix=[[.9]]
    if(change==='round_trip'){u.ticker='B';u.ticker='A'}
    const before=JSON.stringify([store.underlyings,store.corrMatrix])
    wait.resolve(reply(market));await pending
    expect(JSON.stringify([store.underlyings,store.corrMatrix])).toBe(before)
    expect(store.marketDataLoading).toBe(false)
    expect(store.yfStatus).toContain('ignorée')
  })

it.each(['one','all'])('le chargement courant %s applique le marché et conserve sa date',async mode=>{
  const store=usePricingStore();store.underlyings[0].ticker='A'
  vi.stubGlobal('fetch',vi.fn(async url=>reply(String(url).includes('hist_vol')?market:dividend)))
  await (mode==='one'?store.loadYfOne(0):store.loadYfAll())
  expect(store.underlyings[0]).toMatchObject({sigma:37,q:1,vol_level_source:'realized'})
  expect(store.yfStatus).toContain('✓')
})

it('un override pendant la seconde requête dividendes reste conservé',async()=>{
  const store=usePricingStore(),wait=deferred();store.underlyings[0].ticker='A'
  vi.stubGlobal('fetch',vi.fn(url=>String(url).includes('hist_vol')?Promise.resolve(reply(market)):wait.promise))
  const pending=store.loadYfOne(0);await flush();store.underlyings[0].sigma=43
  wait.resolve(reply(dividend));await pending
  expect(store.underlyings[0].sigma).toBe(43)
})

const fit={parameters:{v0:.09,theta:.1,kappa:1.2,xi:.4,rho_h:-.8},success:true,qualified:true,
  calibration_evidence:{version:1,server_signature:'server-test-evidence'}}
const underlying=()=>reactive({ticker:'A',sigma:30,q:2,vol_surface:makeSurface('equity',30),kappa:2})
it('le Pricer explique un refus de qualification et ne transmet aucun prix',async()=>{
  const store=usePricingStore()
  store.script='AT MATURITY:\n  PAY 1';store.globalParams.model='heston'
  Object.assign(store.underlyings[0],underlying())
  vi.stubGlobal('fetch',vi.fn(async url=>reply(url==='/api/volatility/calibrate'
    ? {...fit,qualified:false,qualification:{reasons:['Écart digitale supérieur à 10 pb.']}}
    : {ok:true,params:[],constats:[]})))
  await store.runPricing()
  expect(store.underlyings[0].kappa).toBe(2)
  expect(store.underlyings[0].smile_calibration.status).toBe('unqualified')
  expect(store.error).toMatch(/exploratoire.*digitale/)
  expect(fetch.mock.calls.some(([url])=>url==='/api/price')).toBe(false)
})
it('une calibration lancée à 3 % ne s’applique pas après passage à 4 %',async()=>{
  const wait=deferred(),u=underlying(),context=reactive({model:'heston',horizon:4,rate:3})
  vi.stubGlobal('fetch',()=>wait.promise)
  const pending=calibrateUnderlying(u,'heston',4,3,()=>context)
  const rejection=expect(pending).rejects.toThrow(/changé/)
  context.rate=4;wait.resolve(reply(fit));await rejection
  expect(u.kappa).toBe(2);expect(u.smile_calibration.status).toBe('stale')
})
it.each([true,false])('deux calibrations chevauchées restent indépendantes, ancienne en premier=%s',async oldFirst=>{
  const first=deferred(),last=deferred(),u=underlying()
  const context=reactive({model:'heston',horizon:4,rate:3})
  vi.stubGlobal('fetch',vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(last.promise))
  const old=calibrateUnderlying(u,'heston',4,3,()=>context)
  context.rate=4
  const recent=calibrateUnderlying(u,'heston',4,4,()=>context)
  if(oldFirst){first.resolve(reply(fit));expect(await old).toBe(false);expect(u.smile_calibration.status).toBe('loading')}
  last.resolve(reply({...fit,parameters:{...fit.parameters,kappa:4}}));await recent
  if(!oldFirst){first.resolve(reply(fit));expect(await old).toBe(false)}
  expect(u.kappa).toBe(4);expect(u.smile_calibration.status).toBe('ready')
})
it('le Pricer refuse de transmettre un pricing préparé avec une calibration périmée',async()=>{
  const store=usePricingStore(),wait=deferred()
  store.script='AT MATURITY:\n  PAY 1';store.globalParams.model='heston';store.globalParams.r=3
  Object.assign(store.underlyings[0],underlying())
  vi.stubGlobal('fetch',vi.fn(async url=>url==='/api/volatility/calibrate'?wait.promise:
    reply(url==='/api/parse'?{ok:true,params:[],constats:[]}:{price:1})))
  const pending=store.runPricing()
  await vi.waitFor(()=>expect(fetch.mock.calls.some(([url])=>url==='/api/volatility/calibrate')).toBe(true))
  store.globalParams.r=4;wait.resolve(reply(fit));await pending
  expect(fetch.mock.calls.some(([url])=>url==='/api/price')).toBe(false)
  expect(store.error).toMatch(/changé|contexte/)
})
it('une ancienne préparation ne bloque pas le pricing de la nouvelle calibration',async()=>{
  const store=usePricingStore(),first=deferred(),last=deferred()
  store.script='AT MATURITY:\n  PAY 1';store.globalParams.model='heston';store.globalParams.r=3
  Object.assign(store.underlyings[0],underlying())
  const fits=[]
  vi.stubGlobal('fetch',vi.fn(async url=>{
    if(url==='/api/volatility/calibrate'){fits.push(url);return fits.length===1?first.promise:last.promise}
    return reply(url==='/api/parse'?{ok:true,params:[],constats:[]}:{price:1})
  }))
  const old=store.runPricing();await vi.waitFor(()=>expect(fits).toHaveLength(1))
  store.globalParams.r=4;const recent=store.runPricing();await vi.waitFor(()=>expect(fits).toHaveLength(2))
  last.resolve(reply({...fit,parameters:{...fit.parameters,kappa:4}}));await recent
  first.resolve(reply(fit));await old
  expect(store.result.price).toBe(1);expect(store.error).toBeNull()
  expect(fetch.mock.calls.filter(([url])=>url==='/api/price')).toHaveLength(1)
})

const rfq=()=>({id:1,model_price:100,model_price_at:'2026-10-21T08:00:00Z',model_input_hash:'a',product_terms_version:1,quotes:[]})
it.each(['model_price','model_price_at','model_input_hash','product_terms_version'])(
  'recharger la même RFQ invalide la décomposition si %s change',async field=>{
    const store=useRfqStore(),old=rfq();store.current=old
    store.lastPricing={rfqId:1,result:{price:1,ic95:[.99,1.01]},serverIdentity:JSON.stringify([1,100,old.model_price_at,'a',1])}
    const changed={...old,[field]:field==='model_price'?105:field==='product_terms_version'?2:'changed'}
    vi.stubGlobal('fetch',async()=>reply(changed));await store.fetchOne(1)
    expect(store.current[field]).toBe(changed[field]);expect(store.lastPricing).toBeNull()
  })
it('un rafraîchissement de cotations conserve une décomposition toujours liée au même prix',async()=>{
  const store=useRfqStore(),old=rfq();store.current=old
  store.lastPricing={rfqId:1,result:{price:1},serverIdentity:JSON.stringify([1,100,old.model_price_at,'a',1])}
  vi.stubGlobal('fetch',async()=>reply({...old,quotes:[{id:9,price:102}]}));await store.fetchOne(1)
  expect(store.lastPricing.result.price).toBe(1)
})
it('une ancienne ouverture RFQ ne remplace pas la dernière',async()=>{
  const store=useRfqStore(),a=deferred(),b=deferred()
  vi.stubGlobal('fetch',vi.fn().mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise))
  const first=store.fetchOne(1),second=store.fetchOne(2)
  b.resolve(reply({...rfq(),id:2}));await second;a.resolve(reply(rfq()));await first
  expect(store.current.id).toBe(2)
})
it('une ancienne erreur réseau d’ouverture ne remonte pas après ouverture de B',async()=>{
  const store=useRfqStore();let reject
  const wait=new Promise((_,r)=>{reject=r})
  vi.stubGlobal('fetch',vi.fn().mockReturnValueOnce(wait).mockResolvedValueOnce(reply({...rfq(),id:2})))
  const old=store.fetchOne(1);await store.fetchOne(2);reject(Error('Erreur A'))
  expect(await old).toBeNull();expect(store.current.id).toBe(2)
})
it('une ancienne modification de cotation ne remplace pas une nouvelle lecture du même dossier',async()=>{
  const store=useRfqStore(),wait=deferred();store.current={id:1,quotes:[{id:4,price:100}]}
  vi.stubGlobal('fetch',()=>wait.promise)
  const pending=store.updateQuote(1,4,{price:101});await flush()
  store.current={id:2,quotes:[]};store.current={id:1,quotes:[{id:4,price:105}]}
  wait.resolve(reply({id:4,price:101}));await pending
  expect(store.current.quotes[0].price).toBe(105)
})
it('un ancien polling réseau ne remplace pas une cotation modifiée pendant son attente',async()=>{
  const store=useRfqStore(),wait=deferred();store.current={id:1,quotes:[{id:4,price:100}]}
  vi.stubGlobal('fetch',vi.fn().mockReturnValueOnce(wait.promise).mockResolvedValueOnce(reply({id:4,price:101})))
  const polling=store.refreshNetworkQuotes(1);await store.updateQuote(1,4,{price:101})
  wait.resolve(reply({id:1,quotes:[{id:4,price:100}]}));await polling
  expect(store.current.quotes[0].price).toBe(101)
})

function previewStore(){return reactive({scriptConstats:[{name:'OBS',kind:'schedule'}],
  constatOverrides:{OBS:{first_observation_date:'2028-01-02',end_date:'2029-01-02',frequency:{value:1,unit:'Y'}}},
  underlyings:[],result:{flux_table:{old:{t:.5}}},contractTermsLocked:false})}
function preview(store,currency=reactive({value:'EUR'})){
  scope=effectScope();return scope.run(()=>useObservationPreview(store,()=> '2028-01-02',()=>currency.value))
}
it.each(['dates','currency'])('l’aperçu ignore l’ancien calendrier après changement de %s',async change=>{
  const calls=[],store=previewStore(),currency=reactive({value:'EUR'})
  vi.stubGlobal('fetch',()=>{const wait=deferred();calls.push(wait);return wait.promise})
  const p=preview(store,currency)
  if(change==='dates')store.constatOverrides.OBS.end_date='2030-01-02';else currency.value='USD'
  calls.at(-1).resolve(reply({dates:['2030-01-02'],first_is_observation:true}));await flush()
  calls[0].resolve(reply({dates:['2029-01-02'],first_is_observation:true}));await flush()
  expect(p.datesObservations.value).toEqual(['2030-01-02'])
})
it('un calendrier refusé n’est pas remplacé par les flux de l’ancien prix',async()=>{
  const store=previewStore();vi.stubGlobal('fetch',async()=>reply({detail:'Convention refusée'},422))
  const p=preview(store);await flush()
  expect(p.datesObservations.value).toEqual([]);expect(p.calendarError.value).toContain('refusée')
})
it('les clôtures tardives du ticker A ne remplacent pas celles de B',async()=>{
  const first=deferred(),last=deferred(),store=reactive({scriptConstats:[],constatOverrides:{},underlyings:[{ticker:'A'}],result:{flux_table:{f:{t:.25}}}})
  vi.stubGlobal('fetch',vi.fn().mockReturnValueOnce(first.promise).mockReturnValue(last.promise))
  scope=effectScope();const p=scope.run(()=>useObservationPreview(store,()=> '2010-01-02',()=> 'EUR'))
  store.underlyings[0].ticker='B'
  last.resolve(reply({dates:['2010-01-01'],prices:{B:[100]}}));await flush()
  first.resolve(reply({dates:['2010-01-01'],prices:{A:[50]}}));await flush()
  expect(p.closesPassees.value['2010-01-02']).toEqual({B:100})
})
