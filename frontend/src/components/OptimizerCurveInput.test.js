import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import OptimizerCurveInput from './OptimizerCurveInput.vue'

describe('Optimizer curve table', () => {
  it('renders percentages and tenors as editable numeric fields with accessible labels', async () => {
    const html=await renderToString(createSSRApp({render:()=>h(OptimizerCurveInput,{
      modelValue:[[1,3],[3,3.5]],label:'Courbe de taux zéro',
    })}))
    expect(html).toContain('value="3.50"')
    expect(html).toContain('nœud 2, taux en pourcent')
    expect(html).toContain('type="number"')
    expect(html).not.toContain('textarea')
    expect(html).toContain('Ajouter un nœud')
  })
  it('shows a flat fallback for an empty curve without manufacturing a node', async () => {
    const html=await renderToString(createSSRApp({render:()=>h(OptimizerCurveInput,{
      modelValue:[],label:'Courbe de funding',
    })}))
    expect(html).toContain('niveau plat utilisé')
    expect(html).not.toContain('type="number"')
  })
})
