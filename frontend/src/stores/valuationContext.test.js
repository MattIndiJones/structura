import { beforeEach,afterEach,it,expect,vi } from 'vitest'
import { createPinia,setActivePinia } from 'pinia'
import { usePricingStore } from './pricing.js'

beforeEach(()=>{setActivePinia(createPinia());localStorage.clear()})
afterEach(()=>vi.unstubAllGlobals())
it.each(['runPaths','runProba'])('%s transports the active short-rate and antithetic settings',async action=>{
  const store=usePricingStore()
  store.script='AT MATURITY:\n  PAY 1'
  store.globalParams.model='constant';store.globalParams.antithetic=false
  store.globalParams.rateModel='hull_white';store.globalParams.sigma_r=1;store.globalParams.a_r=.2
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({ok:true,params:[],constats:[]})})))
  await store[action]()
  const call=fetch.mock.calls.find(([url])=>url===(action==='runPaths'?'/api/paths':'/api/proba'))
  expect(call).toBeTruthy()
  expect(JSON.parse(call[1].body)).toMatchObject({antithetic:false,sigma_r:.01,a_r:.2})
})
