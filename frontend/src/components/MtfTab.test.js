import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import MtfTab from './MtfTab.vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'

let pinia
beforeEach(() => {
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.unstubAllGlobals())

it('affiche la graine effective 42 en lecture seule', async () => {
  const html = await renderToString(createSSRApp(MtfTab).use(pinia))
  expect(html).toContain('Graine fixe')
  const input = html.match(/<input[^>]*aria-label="Graine Monte Carlo fixe"[^>]*>/)?.[0]
  expect(input).toBeTruthy()
  expect(input).toContain('value="42"')
  expect(input).toContain('readonly')
})

it('conserve le masquage de la graine en mode démo', async () => {
  useDemoModeStore().enabled = true
  const html = await renderToString(createSSRApp(MtfTab).use(pinia))
  expect(html).not.toContain('aria-label="Graine Monte Carlo fixe"')
  expect(html).toContain('Graine fixe')
  expect(html).toContain('sv-input-mask')
})

it('envoie et conserve la graine effective pour l’éventail et son drill-down', async () => {
  const store = usePricingStore()
  store.script = 'AT MATURITY:\n  PAY 1'
  store.globalParams.T = 1
  store.globalParams.seed = 101
  store.result = { price: 1 }
  vi.stubGlobal('fetch', vi.fn(async url => ({
    ok: true,
    json: async () => String(url).endsWith('/api/parse')
      ? { ok: true, params: [], constats: [], has_maturity_event: true }
      : { results: [] },
  })))
  await store.runMtf({ seed: 202, n_outer: 20, n_inner: 50, n_dates: 2 })
  const call = fetch.mock.calls.find(([url]) => url === '/api/mtf')
  expect(call).toBeTruthy()
  const body = JSON.parse(call[1].body)
  expect(body).toMatchObject({ seed: 42, n_outer: 20, n_inner: 50, n_dates: 2 })
  await store.runMtfDrilldown({ t: .5, ids: [0] })
  const detail = fetch.mock.calls.find(([url]) => url === '/api/mtf/drilldown')
  expect(detail).toBeTruthy()
  expect(JSON.parse(detail[1].body)).toMatchObject({ seed: 42, t: .5, scenario_ids: [0] })
})
