import { describe,expect,it,vi } from 'vitest'
import { createRenderer,createSSRApp,h,nextTick,reactive,ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Results from './OptimizerResearchResults.vue'
import Panel from './OptimizerPanel.vue'
import families from '../utils/__fixtures__/optimizerFamilies.json'
import { payoffMode } from '../utils/optimizerPayoff.js'
vi.mock('chart.js/auto',()=>({default:class {destroy(){}}}))
const family=payoffMode(families.find(f=>f.product_family==='autocall_athena'),'maximize_coupon')
const row=(id,coupon,status='REJECTED',validation='NOT_SELECTED')=>({candidate_id:id,coupon,maturity_months:36,protection_barrier:.6,autocall_trigger:1,fair_value:1,price_ic95:[.99,1.01],probability_loss:.2,probability_autocall:.7,expected_maturity:2,pricing_status:'PRICED',constraint_status:status,validation_status:validation})
const record=()=>({id:'research',status:'COMPLETED',title:'Athena',summary:'Demande complète figée',intention:'Privilégier le coupon',pricing_date:'2026-10-08',progress:{},context:{payoff:family,market_snapshot:{fields:{},warnings:[]}},
  request:{product_family:'autocall_athena',objective:'maximize_coupon',currency:'EUR',market:{underlyings:[{ticker:'TEST',name:'Test'}]},ranges:{maturity_months:{minimum:36,maximum:60,step:12},autocall_trigger:{minimum:1,maximum:1,step:.05},protection_barrier:{minimum:.6,maximum:.6,step:.05}},constraints:{target_price:1,price_tolerance:.005,min_coupon:0,max_coupon:.3},economics:{upfront_fees:0,structuring_margin:0},search:{simulations:4000,seed:42,max_seconds:1800,parallel_workers:2}},
  result:{statistics:{generated:3,priced:3,valid:0,rejected:3},validation:{selected:0,passed:0},candidates:[row('C1',.08),row('C2',.12),row('C3',.1)],request:{objective:'maximize_coupon',constraints:{target_price:1,price_tolerance:.005}}}})
describe('Research result workspace',()=>{
  it('shows saved demand and rejected prices before expandable diagnostics, with accessible help',async()=>{
    const html=(await renderToString(createSSRApp({render:()=>h(Results,{record:record()})}))).replace(/ data-v-[a-f0-9]+/g,'')
    expect(html).toContain('Demande complète figée');expect(html).toContain('Privilégier le coupon')
    expect(html).toContain('Aucune structure confirmée');expect(html).toContain('<tr class="bad">')
    expect(html.indexOf('<b>C2</b>')).toBeLessThan(html.indexOf('<b>C1</b>'))
    expect(html).toContain('<details><summary>Voir les blocages et réglages</summary>')
    expect(html).toContain('aria-label="Afficher l’explication"')
    expect(html).toContain('Marché &amp; calcul')
    expect(html).not.toContain('panel-body-scroll')
    expect(html).not.toContain('max-height:')
    const panel=await renderToString(createSSRApp({render:()=>h(Panel,{title:'Erreurs',height:'35vh'},()=>h('p','Diagnostic'))}))
    expect(panel).not.toContain(' open');expect(panel).toContain('max-height:35vh')
  })
  it('announces provisional solutions during exploration instead of an absence of solutions',async()=>{
    const data=record();data.status='RUNNING';data.result.candidates=[row('WAITING',.1,'PASS')];data.progress={phase:'exploration',completed:23,total:75}
    const html=await renderToString(createSSRApp({render:()=>h(Results,{record:data})}))
    expect(html).toContain('Exploration en cours · 1 structure(s) admissible(s) provisoirement')
    expect(html).not.toContain('Aucune structure confirmée')
    expect(html).toContain('attendre la sélection et la validation indépendante')
    expect(html).not.toContain('Préparer un recalcul')
  })
  it('updates default comparison as background prices arrive and preserves user selection',async()=>{
    const data=reactive(record());data.result.candidates=[row('C1',.08)]
    let state
    const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
    const app=renderer.createApp({setup(props,ctx){state=Results.setup({record:data},ctx);return ()=>null}})
    app.provide(ssrContextKey,{modules:new Set()});app.mount({})
    try {
      expect(state.selected.value).toEqual(['C1'])
      data.result.candidates.push(row('C2',.12),row('C3',.1));await nextTick()
      expect(state.selected.value).toEqual(['C2','C3'])
      state.select(['C1','C3']);data.result.candidates.push(row('C4',.2));await nextTick()
      expect(state.selected.value).toEqual(['C1','C3'])
      expect(state.metrics.value.some(m=>m.key==='probability_autocall')).toBe(true)
    }finally{app.unmount()}
  })
})
