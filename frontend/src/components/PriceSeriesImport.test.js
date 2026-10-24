import { afterEach, expect, it } from 'vitest'
import { createRenderer, createSSRApp, h, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import PriceSeriesImport from './PriceSeriesImport.vue'

const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
let app,state
afterEach(()=>{app?.unmount();app=null})
function setup(){
  const emitted=[]
  app=renderer.createApp({setup(_,context){state=PriceSeriesImport.setup({busy:false},{...context,emit:(...args)=>emitted.push(args)});return()=>null}})
  app.provide(ssrContextKey,{modules:new Set()});app.mount({});return emitted
}

it.each(['currency','price_type','unit'])('un import sans convention %s ne peut pas partir',field=>{
  const emitted=setup()
  Object.assign(state.conventions,{currency:'EUR',price_type:'ADJUSTED_CLOSE',unit:'CURRENCY',[field]:''})
  const event={target:{files:[{name:'prices.json'}],value:'prices.json'}}
  state.chooseFile(event)
  expect(emitted).toEqual([]);expect(state.error.value).toContain('Précisez')
  expect(event.target.value).toBe('')
})
it.each(['ADJUSTED_CLOSE','TOTAL_RETURN_NAV'])('le fichier et les conventions explicites %s sont transmis ensemble',price_type=>{
  const emitted=setup(),file={name:'prices.json'}
  Object.assign(state.conventions,{currency:'eur',price_type,unit:'CURRENCY'})
  state.chooseFile({target:{files:[file],value:'x'}})
  expect(emitted).toEqual([['upload',{file,currency:'EUR',price_type,unit:'CURRENCY',adjustment_date:''}]])
  state.conventions.currency='USD'
  expect(emitted[0][1].currency).toBe('EUR')
})
it('le choix du fichier reste désactivé tant que les conventions sont absentes',async()=>{
  const html=await renderToString(createSSRApp({render:()=>h(PriceSeriesImport,{busy:false})}))
  expect(html).toMatch(/type="file"[^>]*disabled/)
  expect(html).toContain('Cours ajustés des dividendes et splits')
  expect(html).toContain('price_close')
})
