import { describe, expect, it } from 'vitest'
import { createRenderer, createSSRApp, h, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Input from './OptimizerNumberInput.vue'

describe('Optimizer decimal input',()=>{
  it('renders two decimals with a matching step and preserves native constraints',async()=>{
    const html=await renderToString(createSSRApp({render:()=>h(Input,{
      modelValue:28.54,min:0,max:150,required:true,'aria-label':'Volatilité',
    })}))
    expect(html).toContain('value="28.54"')
    expect(html).toContain('step="0.01"')
    expect(html).toContain('min="0"')
    expect(html).toContain('max="150"')
    expect(html).toContain('required')
    expect(html).toContain('aria-label="Volatilité"')
    const zero=await renderToString(createSSRApp({render:()=>h(Input,{modelValue:0})}))
    expect(zero).toContain('value="0.00"')
  })
  it('keeps intermediate entry editable, rounds extra digits and leaves an empty field missing',()=>{
    let state
    const updates=[]
    const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
    const app=renderer.createApp({setup(){
      state=Input.setup({modelValue:28.54},{expose(){},emit:(event,value)=>{if(event==='update:modelValue')updates.push(value)}})
      return ()=>null
    }})
    app.provide(ssrContextKey,{modules:new Set()});app.mount({})
    try {
      state.focus({target:{value:'28.54'}})
      state.edit({target:{value:'1.'}})
      expect(state.draft.value).toBe('1.')
      const target={value:'28.542308'}
      state.edit({target})
      expect(target.value).toBe('28.54')
      expect(updates.at(-1)).toBe(28.54)
      state.edit({target:{value:'0'}})
      expect(updates.at(-1)).toBe(0)
      state.edit({target:{value:''}})
      expect(updates.at(-1)).toBe('')
    } finally {app.unmount()}
  })
})
