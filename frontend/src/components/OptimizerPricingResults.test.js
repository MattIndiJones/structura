import { describe, expect, it } from 'vitest'
import { createSSRApp, h,createRenderer,reactive,ssrContextKey,nextTick } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Panel from './OptimizerPricingResults.vue'

const metrics=[{key:'coupon',label:'Coupon annuel',unit:'pct'},{key:'fair_value',label:'Juste valeur',unit:'pct'}]
const row=(id,coupon)=>({candidate_id:id,coupon,fair_value:1,price_ic95:[.992,1.008],pricing_status:'PRICED',constraint_status:'REJECTED',
  validation_status:'NOT_SELECTED',rejection_details:[{category:'MC_UNCERTAINTY',metric:'fair_value',label:'IC95 hors tolérance',estimate:1,interval:[.992,1.008],target:1,tolerance:.005}]})
async function render(candidates){
  const result={candidates,request:{objective:'maximize_coupon',constraints:{target_price:1,price_tolerance:.005}},validation:{selected:0}}
  return (await renderToString(createSSRApp({render:()=>h(Panel,{result,metrics,selected:[]})}))).replace(/ data-v-[a-f0-9]+/g,'')
}
describe('Visible priced alternatives',()=>{
  it('paginates every price without losing selection between pages and resets paging when sorting changes',async()=>{
    const candidates=Array.from({length:13},(_,i)=>row(`C${i+1}`,(i+1)/100))
    const props=reactive({result:{candidates,request:{objective:'maximize_coupon',constraints:{target_price:1,price_tolerance:.005}}},metrics,selected:[]})
    let state
    const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
    const app=renderer.createApp({setup(_,ctx){state=Panel.setup(props,{...ctx,emit:(event,value)=>{if(event==='update:selected')props.selected=value}});return ()=>null}})
    app.provide(ssrContextKey,{modules:new Set()});app.mount({})
    try {
      expect(state.pages.value).toBe(2);expect(state.visible.value).toHaveLength(10)
      state.toggle('C13',true);state.page.value=2
      expect(state.visible.value.map(c=>c.candidate_id)).toEqual(['C3','C2','C1'])
      state.toggle('C3',true);expect(props.selected).toEqual(['C13','C3'])
      state.sort.value='risk';await nextTick();expect(state.page.value).toBe(1)
      state.limit.value=25;await nextTick();expect(state.visible.value).toHaveLength(13)
    }finally{app.unmount()}
  })
  it('renders three rejected Monte-Carlo prices with red backgrounds and actionable diagnostics',async()=>{
    const html=await render([row('C1',.07),row('C2',.11),row('C3',.09)])
    expect(html).toContain('3 structure(s) pricée(s)')
    for(const id of ['C1','C2','C3']) expect(html).toContain(`<b>${id}</b>`)
    expect(html.indexOf('<b>C2</b>')).toBeLessThan(html.indexOf('<b>C3</b>'))
    expect(html).toContain('11,00 %')
    expect(html).toContain('<tr class="bad">')
    expect(html).toContain('Non confirmée — incertitude Monte-Carlo')
    expect(html).toContain('augmenter les simulations')
    expect(html).toContain('Tolérance couvrant cet intervalle')
  })
  it('colours only confirmed results green and shows actual failed runs separately',async()=>{
    const good={...row('GOOD',.1),constraint_status:'PASS',validation_status:'PASSED',rejection_details:[]}
    const failed={candidate_id:'ERROR',pricing_status:'FAILED',errors:['Erreur moteur']}
    const html=await render([good,failed])
    expect(html).toContain('<tr class="good">')
    expect(html).toContain('Confirmée — conditions respectées')
    expect(html).toContain('Structures non pricées / erreurs (1)')
    expect(html).toContain('Erreur moteur')
    expect(html).toContain('journaux du calcul')
    expect(html).not.toContain('<b>ERROR</b>')
  })
})
