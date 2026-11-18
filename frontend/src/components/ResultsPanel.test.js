import { expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import ResultsPanel from './ResultsPanel.vue'
import { usePricingStore } from '../stores/pricing.js'

it('un strike futur reste à constater et ne charge aucun cours historique', async () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = usePricingStore()
  const closes = vi.spyOn(store, 'loadStrikeCloses')
  store.rightTab = 'results'
  store.result = {
    pre_strike: true, price: .93, ic95: [.92, .94], n_eff: 1000, elapsed_ms: 10,
    payoffs: [], effective_T: 3,
    _inputs: { ...store.globalParams, strike_date: '2026-10-14', valuation_date: '2026-10-07',
      underlyings: [{ ...store.underlyings[0], ticker: 'AXA.PA' }], corrMatrix: [[1]],
      paramOverrides: {}, paramsUsed: [], constats: {}, yieldCurve: { enabled: false, pillars: [] },
      fundingCurve: { enabled: false, pillars: [] } },
  }
  const app = createSSRApp({ render: () => h(ResultsPanel) })
  app.use(pinia)
  const html = await renderToString(app)
  expect(html).toContain('Fixing initial à venir')
  expect(html).toContain('Non encore constaté')
  expect(html).toContain('14/10/2026')
  expect(closes).not.toHaveBeenCalled()
})

async function renderResult(extra) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = usePricingStore()
  store.rightTab = 'results'
  store.result = {
    price: .97, ic95: [.96, .98], n_eff: 1000, elapsed_ms: 10, payoffs: [], effective_T: 1,
    _inputs: { ...store.globalParams, underlyings: [{ ...store.underlyings[0] }], corrMatrix: [[1]],
      paramOverrides: {}, paramsUsed: [], constats: {}, yieldCurve: { enabled: false, pillars: [] },
      fundingCurve: { enabled: false, pillars: [] } },
    ...extra,
  }
  const app = createSSRApp({ render: () => h(ResultsPanel) })
  app.use(pinia)
  return renderToString(app)
}

it('un prix à smile sur 52 pas porte l’avertissement de grille', async () => {
  const html = await renderResult({ grid_notice: 'Grille de 52 pas par an avec un modèle à smile' })
  expect(html).toContain('data-test="grid-notice"')
  expect(html).toContain('Grille de 52 pas par an avec un modèle à smile')
})

it('sans avertissement serveur, aucun encadré de grille', async () => {
  const html = await renderResult({})
  expect(html).not.toContain('data-test="grid-notice"')
})
