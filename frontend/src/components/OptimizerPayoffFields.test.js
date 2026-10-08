import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import families from '../utils/__fixtures__/optimizerFamilies.json'
import { payoffState } from '../utils/optimizerPayoff.js'
import OptimizerPayoffFields from './OptimizerPayoffFields.vue'

async function render(key) {
  const family=families.find(f=>f.product_family===key), state=payoffState(family)
  return renderToString(createSSRApp({render:()=>h(OptimizerPayoffFields,{family,...state,observations:[3]})}))
}

describe('Dynamic payoff form',()=>{
  it('renders each required Phoenix parameter and no step-down control',async()=>{
    const html=await render('phoenix')
    for(const name of ['M_KI_BAR','M_AC_BAR','M_CPN_BAR']) expect(html).toContain(`data-parameter="${name}"`)
    expect(html).toContain('Barrière coupon (%) minimum')
    expect(html).toContain('value="70"')
    expect(html).toContain('Fréquences de constatation')
    expect(html).toContain('Fixe')
    expect(html).toContain('À explorer')
    expect(html).toContain('1 valeur(s) : 70')
    expect(html).not.toContain('aria-label="Plancher de rappel (%)"')
  })
  it('removes inapplicable coupon barrier, autocall and frequency fields',async()=>{
    const html=await render('reverse_convertible')
    expect(html).not.toContain('data-parameter="M_AC_BAR"')
    expect(html).not.toContain('data-parameter="M_CPN_BAR"')
    expect(html).not.toContain('type="checkbox"')
    expect(html).toContain('Constatation unique à maturité')
    expect(html).toContain('COUPON · requis')
  })
  it('array parameter exposes explicit schedule-generation controls only on step-down',async()=>{
    const html=await render('autocall_barriere_degressive')
    expect(html).toContain('Série par constatation')
    expect(html).toContain('aria-label="Plancher de rappel (%)"')
    expect(html).toContain('aria-label="Première constatation avec baisse"')
    expect(html).not.toContain('data-parameter="M_CPN_BAR"')
    expect(await render('autocall_athena')).not.toContain('Barrière coupon (%) minimum')
    expect(await render('phoenix_memoire')).toContain('mémoire non payée')
  })
})
