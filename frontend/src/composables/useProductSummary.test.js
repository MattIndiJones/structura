import { afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePricingStore } from '../stores/pricing.js'
import { buildProductSummary } from './useProductSummary.js'

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it.each([
  ['deterministic', 0, 0], ['abm', .015, 0], ['hull_white', .015, .3],
])('décrit les taux effectifs envoyés au moteur en mode %s', async (mode, sigma, a) => {
  setActivePinia(createPinia())
  const store = usePricingStore()
  store.script = 'AT MATURITY:\n  PAY 1'
  Object.assign(store.globalParams,{T:1,rateModel:mode,sigma_r:1.5,a_r:.3,N:20000,antithetic:true})
  vi.stubGlobal('fetch',vi.fn(async url => ({ok:true,json:async()=>String(url).endsWith('/api/parse')
    ? {ok:true,params:[],constats:[],has_maturity_event:true} : {price:.97}})))
  await store.runPricing()
  expect(store.error).toBeNull()
  const body = JSON.parse(fetch.mock.calls.find(([url])=>url==='/api/price')[1].body)
  expect(body).toMatchObject({sigma_r:sigma,a_r:a})
  expect(store.result._inputs).toMatchObject({sigma_r:sigma*100,a_r:a})
  const summary = buildProductSummary(store).texte
  expect(summary.includes('Taux stochastique')).toBe(sigma>0)
  expect(summary.replaceAll(/[\u00a0\u202f]/g,' ')).toContain('20 000 paires antithétiques (40 000 trajectoires)')
  if(sigma>0) expect(summary).toContain(`a ${a===0?'0,00':'0,30'}`)
})

it('interprète les anciens snapshots déterministes avec des valeurs dormantes et les chemins sans antithétiques',()=>{
  const inputs={model:'constant',rateModel:'deterministic',sigma_r:1.5,a_r:.3,N:20000,seed:42,antithetic:false}
  const summary=buildProductSummary({result:{price:.97,_inputs:inputs}}).texte
  expect(summary).not.toContain('Taux stochastique')
  expect(summary.replaceAll(/[\u00a0\u202f]/g,' ')).toContain('20 000 trajectoires')
  expect(summary).not.toContain('paires antithétiques')
})
