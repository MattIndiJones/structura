import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePricingStore } from './pricing.js'
import { useProductsStore } from './products.js'
import { researchFormState } from '../utils/optimizerResume.js'
import { standardMtmRequest, useBookingMtm, localDay } from '../composables/useBookingMtm.js'
import { compareMarketSnapshots } from '../utils/productCalculations.js'
import { makeSurface } from '../utils/volSurface.js'

const reply = data => ({ ok:true, json:async()=>data })
function parse(script) {
  return {ok:!script.includes('INVALID'), params:[...script.matchAll(/^PARAM(\(\))? +(\w+)(?: *= *([\d.]+)(%?))?/gm)].map(m=>({
    name:m[2],kind:m[1]?'array':'scalar',is_pct:m[4]==='%',display_default:m[3]?Number(m[3]):null})),
  constats:[...script.matchAll(/^CONSTAT(\(\)(?:\(\))?)? +(\w+)/gm)].map(m=>({name:m[2],kind:!m[1]?'single':m[1]==='()'?'schedule':'nested_schedule'}))}
}
const config = changes => ({id:77,name:'Configuration',script_text:'PARAM() COUPON = 8%\nCONSTAT() OBS\nAT MATURITY\n  PAY 1',
  params_json:JSON.stringify({COUPON:[8,null,12]}),constats_json:JSON.stringify({OBS:{start_date:'2026-10-21',end_date:'2028-10-21',frequency:'6M'}}),
  global_params_json:JSON.stringify({configuration:{include_basket:false},deal_ccy:'USD',r:7,model:'heston',N:12000,
    rateModel:'hull_white',sigma_r:2,a_r:.2,funding:{enabled:true,mode:'flat',level:2},
    yield_curve_enabled:true,yield_curve_pillars:[{T:1,rate:6}]}),...changes})

beforeEach(()=>{
  setActivePinia(createPinia())
  vi.stubGlobal('fetch',vi.fn(async(url,options)=>reply(String(url).includes('/api/parse')?parse(JSON.parse(options.body).script):{})))
})
afterEach(()=>vi.unstubAllGlobals())

describe('conservation et reprise C07',()=>{
  it('conserve chaque cellule partielle et refuse son utilisation dans un calcul complet',async()=>{
    const store=usePricingStore();store.script='PARAM() COUPON = 8%\nAT MATURITY\n  PAY 1';await store.parseScript()
    store.paramOverrides.COUPON=[8,'',12]
    expect(store.draftProductBody().user_params.COUPON).toEqual([.08,null,.12])
    expect(()=>store.buildUserParams()).toThrow('ligne 2')
    store.paramOverrides.COUPON[1]=10
    expect(store.buildUserParams().COUPON).toEqual([.08,.1,.12])
  })

  it('exige le choix explicite de la ligne scalaire et restitue la série au retour',async()=>{
    const store=usePricingStore();store.script='PARAM() COUPON = 8%\nAT MATURITY\n  PAY 1';await store.parseScript()
    store.paramOverrides.COUPON=[8,10,12];store.script=store.script.replace('PARAM()','PARAM');await store.validateScript()
    expect(store.parameterConversions.COUPON).toEqual([8,10,12]);expect(()=>store.buildUserParams()).toThrow('conversion')
    store.confirmParameterConversion('COUPON',2);expect(store.buildUserParams().COUPON).toBe(.12)
    store.script=store.script.replace('PARAM ','PARAM() ');await store.validateScript()
    expect(store.paramOverrides.COUPON).toEqual([8,10,12])
  })

  it('construit une forme de calendrier valide sans inventer de dates et restaure la date unique',async()=>{
    const store=usePricingStore();store.script='CONSTAT OBS\nAT OBS\n  PAY 1';await store.parseScript()
    store.constatOverrides.OBS={date:'2027-10-21',convention:'following',settlement_lag:3,observation_calendars:['NYSE'],observation_join:'all_open'}
    store.script=store.script.replace('CONSTAT ','CONSTAT() ');await store.validateScript()
    expect(store.constatOverrides.OBS).toMatchObject({start_date:'',end_date:'',frequency:{value:null,unit:'M'},convention:'following',observation_calendars:['NYSE']})
    expect(store.buildConstats().OBS).toMatchObject({observation_join:'all_open',observation_calendars:['NYSE']})
    store.script=store.script.replace('CONSTAT() ','CONSTAT ');await store.validateScript()
    expect(store.constatOverrides.OBS.date).toBe('2027-10-21')
  })

  it.each(['params_json','global_params_json','constats_json'])('un JSON invalide laisse toute la session intacte : %s',async key=>{
    const store=usePricingStore();store.globalParams.r=4.321;store.paramOverrides.OLD=[1,2];store.result={price:.99}
    const before=JSON.stringify(store.$state)
    await expect(store.loadFromDb(config({[key]:'{invalid'}))).rejects.toThrow('JSON invalide')
    expect(JSON.stringify(store.$state)).toBe(before)
  })

  it('un parsing refusé ne touche ni les termes, ni le marché, ni le résultat',async()=>{
    const store=usePricingStore();store.result={price:.99};store.globalParams.r=4.321
    const before=JSON.stringify(store.$state)
    await expect(store.loadFromDb(config({script_text:'INVALID'}))).rejects.toThrow('Configuration refusée')
    expect(JSON.stringify(store.$state)).toBe(before)
  })

  it('une date unique enregistrée pour un échéancier est refusée avant remplacement',async()=>{
    const store=usePricingStore(),before=JSON.stringify(store.$state)
    await expect(store.loadFromDb(config({constats_json:JSON.stringify({OBS:'2027-01-01'})}))).rejects.toThrow('incompatible')
    expect(JSON.stringify(store.$state)).toBe(before)
  })

  it.each([{underlyings:[{sigma:'invalid'}]}, {underlyings:[{vol_surface:{eta:1}}]}, {funding:{pillars:[null]}},
    {model:'unknown'}, {corr_matrix:[[1,2]]}, {r:'invalid'}, {funding:null}, {yield_curve_enabled:true},
    {underlyings:[{sigma:20}]}, {funding:{enabled:true,mode:'pillars'}}])('une configuration mal formée est refusée avant mutation : %j',async saved=>{
    const store=usePricingStore(),before=JSON.stringify(store.$state)
    await expect(store.loadFromDb(config({global_params_json:JSON.stringify(saved)}))).rejects.toThrow()
    expect(JSON.stringify(store.$state)).toBe(before)
  })

  it('applique seulement les termes en préservant panier, taux, funding et modèle',async()=>{
    const store=usePricingStore();store.underlyings[0].ticker='KEEP';store.globalParams.r=4.321;store.globalParams.model='lsv'
    store.fundingCurve.enabled=true;store.fundingCurve.level=1.234;store.yieldCurve.enabled=true
    const old=JSON.stringify([store.underlyings,store.corrMatrix,store.yieldCurve,store.fundingCurve])
    await store.loadFromDb(config(),{scope:'terms'})
    expect(JSON.stringify([store.underlyings,store.corrMatrix,store.yieldCurve,store.fundingCurve])).toBe(old)
    expect(store.globalParams).toMatchObject({r:4.321,model:'lsv',deal_ccy:'USD'})
    expect(store.paramOverrides.COUPON).toEqual([8,null,12])
  })

  it('applique toutes les hypothèses seulement dans la portée choisie',async()=>{
    const store=usePricingStore();store.underlyings[0].ticker='KEEP'
    await store.loadFromDb(config(),{scope:'all'})
    expect(store.globalParams).toMatchObject({r:7,model:'heston',rateModel:'hull_white',sigma_r:2})
    expect(store.fundingCurve).toMatchObject({enabled:true,level:2});expect(store.yieldCurve.pillars).toEqual([{T:1,rate:6}])
    expect(store.underlyings[0].ticker).toBe('KEEP')
  })

  it('applique un panier et ses corrélations quand leur inclusion a été choisie',async()=>{
    const store=usePricingStore()
    await store.loadFromDb(config({global_params_json:JSON.stringify({configuration:{include_basket:true},
      underlyings:[{name:'A',ticker:'A',ccy:'EUR',sigma:21},{name:'B',ticker:'B',ccy:'EUR',sigma:23}],corr_matrix:[[1,.4],[.4,1]]})}),{scope:'all'})
    expect(store.underlyings.map(u=>u.ticker)).toEqual(['A','B']);expect(store.corrMatrix).toEqual([[1,.4],[.4,1]])
  })

  it('refuse de remplacer des termes Product conservés par une configuration',async()=>{
    const store=usePricingStore();store.currentProduct={product_id:1}
    await expect(store.loadFromDb(config())).rejects.toThrow('figés')
    expect(store.currentProduct.product_id).toBe(1)
  })

  it('ne remplace pas une saisie survenue pendant la validation de configuration',async()=>{
    const store=usePricingStore();let release
    vi.stubGlobal('fetch',vi.fn(()=>new Promise(resolve=>{release=resolve})))
    const loading=store.loadFromDb(config());store.globalParams.r=9
    release(reply(parse(config().script_text)))
    await expect(loading).rejects.toThrow('session a changé');expect(store.globalParams.r).toBe(9)
  })

  it('ouvre la version courante sans importer le calcul historique',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>reply({product_id:1,terms_version:2,calculations:[{id:3,terms_version:1}]})))
    const loaded=await useProductsStore().fetchOne(1)
    expect(loaded.calculationInput).toBeNull();expect(loaded.product.terms_version).toBe(2);expect(loaded.notice).toContain('Aucun calcul')
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
  })

  it('ouvre un Product partiel et permet une modification explicite sans débloquer un dossier booké',async()=>{
    const store=usePricingStore()
    const product={product_id:1,revision:1,terms_version:1,reference:'P1',terms:{script:'PARAM() COUPON = 8%\nAT MATURITY\n  PAY 1',
      T:null,underlyings:[{name:'A',ticker:'A',ccy:'EUR'}],parameters:[{name:'COUPON',value:[.08,null,.12]}],constats:{}}}
    await store.loadFromProduct(product)
    expect(store.contractTermsLocked).toBe(true);expect(store.paramOverrides.COUPON).toEqual([8,null,12])
    store.beginProductTermsEdit();expect(store.contractTermsLocked).toBe(false);expect(store.currentProduct.product_id).toBe(1)
    await store.runPaths();expect(store.error).toContain('Conservez la nouvelle version')
    store.currentProduct={...product,execution:{deal_id:7}}
    expect(()=>store.beginProductTermsEdit()).toThrow('modification directe')
  })

  it('recharge la précision et tous les buckets du marché conservé sans les regénérer',async()=>{
    const store=usePricingStore()
    const product={product_id:1,reference:'P1',terms:{script:'AT MATURITY\n  PAY 1',T:3,underlyings:[{name:'A',ticker:'A',ccy:'EUR'}],parameters:[],constats:{}}}
    const market={r:.030012345,underlyings:[{q:.02001,sigma:.200012345,dividend_curve:[[1,.02001],[2,.019],[3,.0187]]}]}
    await store.loadFromProduct(product,market)
    const body=store.pricingBody()
    expect(body.r).toBeCloseTo(market.r,15)
    expect(body.underlyings[0].sigma).toBeCloseTo(market.underlyings[0].sigma,15)
    expect(body.underlyings[0].dividend_curve).toEqual(market.underlyings[0].dividend_curve)
  })

  it('les changements de calendriers de la copie de travail ne modifient pas le Product reçu',async()=>{
    const store=usePricingStore()
    const product={product_id:1,terms:{script:'CONSTAT() OBS\nAT OBS\n  PAY 1',T:1,underlyings:[],parameters:[],
      constats:{OBS:{frequency:'1Y',observation_calendars:['NYSE'],observation_join:'all_open'}}}}
    await store.loadFromProduct(product);store.beginProductTermsEdit()
    store.constatOverrides.OBS.observation_calendars.push('XETR')
    expect(product.terms.constats.OBS.observation_calendars).toEqual(['NYSE'])
    expect(store.buildConstats().OBS.observation_calendars).toEqual(['NYSE','XETR'])
  })

  it('compare eta et les paramètres de taux, avec unités et paramètres inactifs explicites',()=>{
    const prior={model:'local_vol',rateModel:'hull_white',sigma_r:1,a_r:.3,underlyings:[{ticker:'A',sigma:20,vol_surface:makeSurface('index',20)}]}
    const current=structuredClone(prior);current.underlyings[0].vol_surface.eta+=.1;current.sigma_r=2
    const rows=compareMarketSnapshots(current,prior)
    expect(rows.find(r=>r.key==='ul:0:surface:eta')).toMatchObject({changed:true,unit:'number',active:true})
    expect(rows.find(r=>r.key==='sigma_r')).toMatchObject({changed:true,delta:1,unit:'percent',active:true})
    const inactive=compareMarketSnapshots({...current,model:'constant',rateModel:'deterministic'},current)
    expect(inactive.find(r=>r.key==='ul:0:surface:eta').label).toContain('inactif')
    expect(inactive.find(r=>r.key==='a_r').active).toBe(false)
  })

  it.each([{funding_spread:0},{funding_spread:.01},{funding_curve:[]},{funding_curve:[[1,.01]]},{funding_source_reference:'Curve'},{future_option:true}])('exclut les runs personnalisés de la reprise standard : %j',async funding=>{
    const request={recalibrate:'none',...funding};expect(standardMtmRequest(request)).toBe(false)
    vi.stubGlobal('fetch',vi.fn(async()=>reply([{deal_id:1,created_at:new Date().toISOString(),diagnostics:{request},result:{mtm:1,valuation_date:localDay()}}])))
    const mtm=useBookingMtm();await mtm.loadSavedMtm(1);expect(mtm.mtmResults[1]).toBeUndefined()
  })

  it('reprend q=2,001 % et son premier bucket sans arrondi ni divergence',()=>{
    const request={market:{underlyings:[{ticker:'A',asset_type:'index',sigma:.2000123,q:.02001,dividend_curve:[[1,.02001]]}],correlation:[[1]],
      rate:.0300123,funding_spread:.0100123},ranges:{},payoff_settings:{},constraints:{},economics:{}}
    const state=researchFormState({request,context:{}},{range_fields:[],fixed_fields:[],solved_field:{}})
    expect(state.assets[0].dividend).toBe(2.001);expect(state.assets[0].dividendCurve[0][1]).toBe(2.001)
    expect(state.assets[0].vol/100).toBeCloseTo(request.market.underlyings[0].sigma,15)
    expect(state.rate/100).toBeCloseTo(request.market.rate,15)
    expect(state.fundingSpread/10000).toBeCloseTo(request.market.funding_spread,15)
  })
})
