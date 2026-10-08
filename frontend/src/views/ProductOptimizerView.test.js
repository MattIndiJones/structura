import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, ssrContextKey, reactive } from 'vue'
import families from '../utils/__fixtures__/optimizerFamilies.json'
import View from './ProductOptimizerView.vue'
import PayoffFields from '../components/OptimizerPayoffFields.vue'
import { payoffState } from '../utils/optimizerPayoff.js'

const mocks=vi.hoisted(()=>({json:vi.fn(),run:vi.fn(),requests:[],references:[],api:vi.fn(),push:vi.fn(),route:{query:{}}}))
vi.mock('../stores/demoMode.js',()=>({useDemoModeStore:()=>({enabled:false})}))
vi.mock('../data/commonUnderlyings.js',()=>({underlyingGroups:[{items:[
  {ticker:'STMPA.PA',label:'STMicro',ccy:'EUR',asset_class:'equity'},
  {ticker:'BNP.PA',label:'BNP',ccy:'EUR',asset_class:'equity'},
  {ticker:'^FCHI',label:'CAC 40',ccy:'EUR',asset_class:'index'},
]}],ensureUnderlyings:async()=>{}}))
vi.mock('../utils/productOptimizer.js',async importOriginal=>({...await importOriginal(),optimizerJson:(...args)=>mocks.json(...args),runOptimizer:(...args)=>mocks.run(...args)}))
vi.mock('vue-router',async importOriginal=>({...await importOriginal(),useRoute:()=>mocks.route,useRouter:()=>({push:mocks.push})}))
vi.mock('../utils/optimizerResearch.js',async importOriginal=>({...await importOriginal(),researchApi:(...args)=>mocks.api(...args)}))
vi.mock('chart.js/auto',()=>({default:class {destroy(){}}}))

let mounted, state
// Vitest compiles Vue templates for SSR. Mount the real setup with a minimal
// renderer to exercise lifecycle hooks, watchers and requests in client order.
const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
async function settle(){for(let i=0;i<5;i++)await nextTick()}
async function load(){await vi.advanceTimersByTimeAsync(260);await settle()}
function reference(ticker,date){
  const sigma=ticker==='STMPA.PA'?.31:.25
  return {pricing_date:date,captured_at:'2026-10-08T14:00:00Z',warnings:[],correlation:[[1]],underlyings:[{ticker,asset_type:ticker==='^FCHI'?'index':'equity',sigma,q:.004,warnings:[]}],
    provenance:{[`underlyings.${ticker}.sigma`]:{source:'HISTORICAL_ESTIMATE',as_of:date,reference_value:sigma,method:'Vol réalisée',provider:'QA'}}}
}
beforeEach(async()=>{
  vi.useFakeTimers();mocks.json.mockReset();mocks.run.mockReset();mocks.api.mockReset();mocks.push.mockReset();mocks.route.query={};mocks.requests=[];mocks.references=[]
  mocks.api.mockResolvedValue({id:'saved-research'})
  mocks.json.mockImplementation(async(path,body)=>{
    if(path==='capabilities')return {families}
    if(path==='market-reference'){mocks.references.push(body);return reference(body.tickers[0],body.pricing_date)}
    if(path==='estimate-search'){mocks.requests.push(body);return {allowed:true,candidate_count:1,budget:{estimated_peak_mb:100},reasons:[]}}
    return {stopping:true}
  })
  mocks.run.mockImplementation(async(body,signal,onEvent)=>{onEvent({type:'run_registered',run_id:'owned-token'})})
  mounted=renderer.createApp({setup(props,ctx){state=View.setup(props,ctx);return ()=>null}})
  mounted.provide(ssrContextKey,{modules:new Set()});mounted.mount({});await settle()
})
afterEach(()=>{mounted?.unmount();vi.useRealTimers()})

describe('Optimizer view lifecycle and request workflow',()=>{
  it('loads a higher-precision draft with the original market, economics and contractual constraints',async()=>{
    state.assets.value[0].ticker='STMPA.PA';await load();state.form.convention='modified_following'
    const original=state.requestBody(),record={id:'origin',title:'Prix à affiner',intention:'Coupon maximum',request:original,context:{payoff:state.activeFamily.value,market_snapshot:{warnings:[]}}}
    mounted.unmount();mocks.route.query={from:'origin',simulations:'16000'};mocks.api.mockResolvedValueOnce(record)
    mounted=renderer.createApp({setup(props,ctx){state=View.setup(props,ctx);return ()=>null}})
    mounted.provide(ssrContextKey,{modules:new Set()});mounted.mount({});await settle()
    expect(state.requestBody()).toEqual({...original,search:{...original.search,simulations:16000}})
    expect(mocks.api).toHaveBeenLastCalledWith('/origin')
    expect(mocks.api.mock.calls.every(call=>call[1]!=='POST')).toBe(true)
  })
  it('saves intention and inputs then opens the dedicated result page without streaming',async()=>{
    state.assets.value[0].ticker='STMPA.PA';await load();state.form.convention='modified_following'
    state.intention.value='Privilégier le coupon, protection à 60 %';state.title.value='Athena STMicro'
    await state.start();await settle()
    const [path,method,command]=mocks.api.mock.calls.at(-1)
    expect([path,method]).toEqual(['','POST'])
    expect(command).toMatchObject({title:'Athena STMicro',intention:state.intention.value,parent_id:null,optimization:{pricing_date:state.form.strike_date}})
    expect(command.command_key).toBeTruthy()
    expect(mocks.push).toHaveBeenCalledWith('/structuring/researches/saved-research')
    expect(mocks.run).not.toHaveBeenCalled()
  })
  it('sends the displayed rounded inputs and restores them without rounding the source snapshot',async()=>{
    const raw=reference('BNP.PA','2026-10-08')
    raw.underlyings[0].sigma=.28542308;raw.underlyings[0].q=.064559
    raw.provenance['underlyings.BNP.PA.sigma'].reference_value=.28542308
    mocks.json.mockImplementation(async(path,body)=>{
      if(path==='market-reference')return raw
      if(path==='estimate-search'){mocks.requests.push(body);return {allowed:true,candidate_count:1,budget:{estimated_peak_mb:100},reasons:[]}}
    })
    state.assets.value[0].ticker='BNP.PA';await load()
    const asset=state.assets.value[0]
    expect(asset).toMatchObject({vol:28.54,dividend:6.46})
    asset.vol=35;asset.manual.vol=true
    state.resetAssetReference(asset,'vol','sigma')
    expect(asset.vol).toBe(28.54);expect(asset.manual.vol).toBe(false)
    state.form.convention='modified_following';await state.start()
    const market=mocks.requests.at(-1).market
    expect(market.underlyings[0].sigma).toBeCloseTo(.2854,12)
    expect(market.underlyings[0].q).toBeCloseTo(.0646,12)
    expect(market.provenance['underlyings.BNP.PA.sigma'].reference_value).toBe(.28542308)
  })
  it('loads from its own title selection, classifies STMicro and sends pricing date',async()=>{
    state.assets.value[0].ticker='STMPA.PA';await load()
    expect(mocks.references).toHaveLength(1)
    expect(state.assets.value[0]).toMatchObject({asset_type:'equity',classified:true,vol:31,dividend:.4})
    state.form.convention='modified_following';await state.start()
    const body=mocks.requests.at(-1)
    expect(body.market.underlyings[0]).toMatchObject({ticker:'STMPA.PA',asset_type:'equity',sigma:.31,q:.004})
    expect(body.pricing_date).toBe(body.market.as_of)
    expect(body.search).toMatchObject({max_candidates:256,max_seconds:1800,simulations:4000})
  })
  it('preserves a manual vol on date change but clears it when replacing the title',async()=>{
    state.assets.value[0].ticker='STMPA.PA';await load()
    state.assets.value[0].vol=42;state.assets.value[0].manual.vol=true
    state.form.strike_date='2026-10-04';await load()
    expect(state.assets.value[0].vol).toBe(42)
    state.assets.value[0].ticker='BNP.PA'
    expect(state.assets.value[0].vol).toBeNull()
    await load();expect(state.assets.value[0].vol).toBe(25)
  })
  it('ignores a response that arrives after a different title was selected',async()=>{
    let release
    mocks.json.mockImplementation(async(path,body)=>{
      if(path==='market-reference' && body.tickers[0]==='STMPA.PA')return new Promise(resolve=>{release=()=>resolve(reference('STMPA.PA',body.pricing_date))})
      return reference('BNP.PA',body.pricing_date)
    })
    state.assets.value[0].ticker='STMPA.PA';await load()
    state.assets.value[0].ticker='BNP.PA';await load()
    release();await settle()
    expect(state.assets.value[0].vol).toBe(25)
    expect(state.automaticMarket.value.underlyings[0].ticker).toBe('BNP.PA')
  })
  it('blocks missing values after an outage and preserves an explicit zero override',async()=>{
    mocks.json.mockRejectedValue(Error('Marché indisponible'))
    state.assets.value[0].ticker='STMPA.PA';await load()
    expect(state.marketError.value).toContain('Marché indisponible')
    state.form.convention='modified_following'
    expect(()=>state.requestBody()).toThrow('numérique obligatoire')
    state.assets.value[0].vol=30;state.assets.value[0].dividend=0
    expect(state.requestBody().market.underlyings[0].q).toBe(0)
  })
  it('an explicit fixed parameter becomes a singleton and the explorer keeps every selected value',async()=>{
    const family=families.find(f=>f.product_family==='phoenix'),initial=payoffState(family)
    const props=reactive({family,...initial,observations:[3]});let fields
    const app=renderer.createApp({setup(){fields=PayoffFields.setup(props,{expose(){},emit:(event,value)=>{if(event==='update:ranges')props.ranges=value}});return ()=>null}})
    app.provide(ssrContextKey,{modules:new Set()});app.mount({})
    try {
      expect(fields.isFixed('protection_barrier')).toBe(true)
      fields.updateRange('protection_barrier','minimum','55')
      expect(props.ranges.protection_barrier).toMatchObject({minimum:55,maximum:55})
      fields.setMode(family.range_fields.find(f=>f.key==='protection_barrier'),'explore')
      fields.updateRange('protection_barrier','maximum','65')
      expect(fields.axisValues('protection_barrier')).toBe('3 valeur(s) : 55 · 60 · 65')
    } finally {app.unmount()}
  })
  it('retries an unknown launch outcome with the identical command and creates a new key after editing',async()=>{
    state.assets.value[0].ticker='STMPA.PA';await load();state.form.convention='modified_following'
    mocks.api.mockRejectedValueOnce(Error('Connexion perdue après lancement'))
    await state.start();expect(state.error.value).toContain('Connexion perdue')
    await state.start()
    expect(mocks.api.mock.calls[0][2]).toEqual(mocks.api.mock.calls[1][2])
    state.intention.value='Autre objectif';await state.start()
    expect(mocks.api.mock.calls[2][2].command_key).not.toBe(mocks.api.mock.calls[0][2].command_key)
    mounted.unmount();mounted=null
    expect(mocks.api.mock.calls.every(call=>call[0]==='')).toBe(true)
  })
  it('resumes a frozen request with curves and overrides into a new linked version',async()=>{
    state.assets.value[0].ticker='STMPA.PA';await load();state.form.convention='modified_following'
    state.form.product_family='phoenix_memoire';await settle()
    state.assets.value[0].vol=42;state.assets.value[0].dividend=2;state.assets.value[0].dividendCurve=[[1,2],[2,1]]
    state.rate.value=4;state.yieldNodes.value=[[1,3],[5,4]];state.fundingMode.value='curve';state.fundingNodes.value=[[1,1],[5,1.5]]
    state.economics.upfront_fees=1;state.risk.loss=25;state.observations.value=[3,6]
    const original=state.requestBody(), family=state.activeFamily.value
    const record={id:'origin',title:'Demande figée',intention:'Recherche phoenix',request:original,context:{payoff:family,market_snapshot:{warnings:[]}}}
    mocks.api.mockResolvedValueOnce(record)
    const referenceCalls=mocks.references.length
    await state.restore('origin');await load()
    expect(mocks.references).toHaveLength(referenceCalls)
    expect(state.requestBody()).toEqual(original)
    await state.start()
    expect(mocks.api.mock.calls.at(-1)[2]).toMatchObject({parent_id:'origin',optimization:original,title:record.title,intention:record.intention})
    state.form.strike_date='2026-10-04';await load()
    expect(mocks.references.length).toBeGreaterThan(referenceCalls)
    expect(state.assets.value[0].vol).toBe(42)
  })

})
