import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import EconomicsTab from './EconomicsTab.vue'
import RfqParamsEditor from './RfqParamsEditor.vue'
import { usePricingStore } from '../stores/pricing.js'
import { preparePreset } from '../utils/payscriptPresets.js'
import { presetServer } from '../utils/__fixtures__/payscriptPresetServer.js'

describe('un exemple dégressif rend les tableaux de paramètres', () => {
  async function terms() {
    const pinia = createPinia()
    setActivePinia(pinia)
    globalThis.fetch = presetServer()
    const plan = await preparePreset('autocall_stepdown_5y', { startDate: '2026-10-07' }, presetServer())
    const store = usePricingStore()
    await store.loadFromPreset(plan)
    return { pinia, store }
  }

  it('Economics affiche les cinq barrières et les réglages avancés sans erreur de rendu', async () => {
    const { pinia } = await terms()
    const app = createSSRApp({ render: () => h(EconomicsTab) })
    app.use(pinia)
    const html = await renderToString(app)
    expect(html).toContain('Obs 5')
    expect(html).toContain('value="80"')
    expect(html).toContain('Réglages avancés du calendrier')
  })

  it('RFQ affiche les cinq barrières et le même calendrier', async () => {
    const { pinia, store } = await terms()
    const app = createSSRApp({ render: () => h(RfqParamsEditor, {
      parsedParams: store.scriptParams, paramOverrides: store.paramOverrides,
      constats: store.scriptConstats, constatOverrides: store.constatOverrides, currency: 'EUR',
    }) })
    app.use(pinia)
    const html = await renderToString(app)
    expect(html).toContain('value="80"')
    expect(html).toContain('value="95"')
    expect(html).toContain('Réglages avancés du calendrier')
    expect(html).not.toContain('Mode Expert')
  })
})
