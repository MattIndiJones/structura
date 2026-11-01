import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, h, nextTick, reactive, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import CalendarPolicyFields from './CalendarPolicyFields.vue'
import { useCalendarDefaults } from '../composables/useCalendarDefaults.js'
import { usePricingStore } from '../stores/pricing.js'

const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
const flush = async () => { for (let i = 0; i < 8; i++) await nextTick() }
let app, state
beforeEach(() => {
  setActivePinia(createPinia()); localStorage.clear()
  vi.stubGlobal('fetch', async () => ({ ok: true, json: async () => ({ observation_codes: ['XMIL','XPAR','TARGET'], settlement_codes: ['TARGET','USD'] }) }))
})
afterEach(() => { app?.unmount(); app = null; vi.unstubAllGlobals() })
async function mount(props) {
  app = renderer.createApp({ setup() { state = useCalendarDefaults(props); return () => null } })
  app.mount({}); await flush(); return state
}
const properties = changes => reactive({ values: {}, currency: 'EUR', underlyings: [{ ticker: 'STMMI.MI' }], frozen: false, ...changes })

it('sépare Milan pour STM et TARGET pour le règlement EUR, puis suit la devise du deal', async () => {
  const props = properties(); await mount(props)
  expect(props.values).toMatchObject({ observation_calendars: ['XMIL'], settlement_calendars: ['TARGET'], observation_join: 'all_open' })
  props.currency = 'USD'; await flush()
  expect(props.values.observation_calendars).toEqual(['XMIL'])
  expect(props.values.settlement_calendars).toEqual(['USD'])
})

it('suit les sous-jacents et déduplique leurs places sans modifier la combinaison du règlement', async () => {
  const props = properties(); await mount(props)
  props.underlyings.push({ ticker: 'CS.PA' }, { ticker: 'BNP.PA' }); await flush()
  expect(props.values.observation_calendars).toEqual(['XMIL','XPAR'])
  expect(props.values.observation_join).toBe('all_open')
  expect(props.values.settlement_calendars).toEqual(['TARGET'])
})

it('préserve les surcharges de chaque champ et permet un retour explicite au défaut', async () => {
  const props = properties(); await mount(props)
  state.customize('observation', ['NYSE']); state.customize('settlement', ['GBP'])
  props.underlyings[0].ticker = 'CS.PA'; props.currency = 'CHF'; await flush()
  expect(props.values.observation_calendars).toEqual(['NYSE'])
  expect(props.values.settlement_calendars).toEqual(['GBP'])
  state.reset('settlement')
  expect(props.values.settlement_calendars).toEqual(['CHF'])
  expect(props.values.observation_calendars).toEqual(['NYSE'])
})

it('conserve les choix explicites d’un calendrier chargé, même EUR pour l’observation', async () => {
  const props = properties({ values: { observation_calendars: ['EUR'], observation_join: 'any_open', settlement_calendars: ['USD','GBP'], settlement_join: 'all_open' } })
  const before = JSON.stringify(props.values); await mount(props)
  props.currency = 'CHF'; await flush()
  expect(JSON.stringify(props.values)).toBe(before)
  state.reset('observation'); expect(props.values.observation_calendars).toEqual(['XMIL'])
})

it('ne modifie aucun terme d’un contrat figé, même si ses anciens choix sont implicites', async () => {
  const props = properties({ frozen: true, values: { date: '2026-12-24', convention: 'following' } })
  const before = JSON.stringify(props.values); await mount(props)
  state.reset('observation'); state.customize('settlement', ['USD'])
  props.currency = 'USD'; await flush()
  expect(JSON.stringify(props.values)).toBe(before)
})

it('retrouve le mode automatique après fermeture et réouverture du composant', async () => {
  const props = properties(); await mount(props)
  app.unmount(); await mount(props)
  props.currency = 'JPY'; await flush()
  expect(props.values.settlement_calendars).toEqual(['JPY'])
})

it('respecte une sélection vidée ou une surcharge reçue depuis un autre contrôle', async () => {
  const props = properties(); await mount(props)
  state.customize('observation', [])
  props.values.settlement_calendars = ['GBP']
  props.currency = 'USD'; await flush()
  expect(props.values.observation_calendars).toEqual([])
  expect(props.values.settlement_calendars).toEqual(['GBP'])
})

it('signale l’approximation bancaire d’un ticker sans place identifiable', async () => {
  const props = properties({ underlyings: [{ ticker: 'UNKNOWN' }] }); await mount(props)
  expect(state.suggested.value.approximation).toBe(true)
  expect(state.suggested.value.unresolved).toEqual(['UNKNOWN'])
  expect(props.values.observation_calendars).toEqual(['TARGET'])
  props.underlyings[0].exchange = 'NMS'; await flush()
  expect(props.values.observation_calendars).toEqual(['NASDAQ'])
  expect(state.suggested.value.approximation).toBe(false)
})

it('ne conserve pas un ancien défaut de règlement quand la nouvelle devise est inconnue', async () => {
  const props = properties(); await mount(props)
  props.currency = 'XXX'; await flush()
  expect(props.values.settlement_calendars).toEqual([])
  expect(props.values.observation_calendars).toEqual(['XMIL'])
})

it('replie les choix et masque la combinaison uniquement pour une sélection unique', async () => {
  const render = values => renderToString(createSSRApp({ render: () => h(CalendarPolicyFields, { values, currency: 'EUR', underlyings: [{ ticker: 'STMMI.MI' }] }) }))
  const single = await render({ observation_calendars: ['XMIL'], settlement_calendars: ['TARGET'] })
  expect(single).toContain('<details'); expect(single).not.toContain('<select')
  expect(single).toContain('Milan'); expect(single).not.toContain('multiple')
  const multiple = await render({ observation_calendars: ['XMIL','XPAR'], observation_join: 'any_open', settlement_calendars: ['TARGET'] })
  expect(multiple).toContain('Combinaison des places'); expect(multiple).not.toContain('Combinaison des centres')
  expect(multiple).toContain('aucun fixing')
})

it('applique les mêmes défauts au corps de calcul sans visiter Economics et préserve le contrat chargé', async () => {
  const store = usePricingStore()
  store.script = 'CONSTAT() OBS\nAT OBS:\n  PAY 1'
  store.underlyings[0].ticker = 'STMMI.MI'
  vi.stubGlobal('fetch', async () => ({ ok: true, json: async () => ({ ok: true, params: [], constats: [{ name: 'OBS', kind: 'schedule' }] }) }))
  await store.validateScript()
  expect(store.buildConstats().OBS).toMatchObject({ observation_calendars: ['XMIL'], settlement_calendars: ['TARGET'] })
  store.globalParams.deal_ccy = 'USD'
  expect(store.buildConstats().OBS.settlement_calendars).toEqual(['USD'])
  store.openedDeal = { id: 1 }
  store.globalParams.deal_ccy = 'GBP'
  expect(store.buildConstats().OBS.settlement_calendars).toEqual(['USD'])
})
