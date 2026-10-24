import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, reactive, ssrContextKey } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import EconomicsTab from './EconomicsTab.vue'
import { usePricingStore } from '../stores/pricing.js'
import { useObservationPreview } from '../composables/useObservationPreview.js'
import CalendarPolicyFields from './CalendarPolicyFields.vue'
import ObservationSchedule from './ObservationSchedule.vue'
import { serializeCalendars } from '../utils/payscriptEconomics.js'

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock('../utils/api.js', () => ({ apiFetch: (...args) => mocks.fetch(...args) }))
const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
let app, state, store
const response = data => ({ ok: true, json: async () => data })
async function flush() { for (let i = 0; i < 12; i++) await nextTick() }
async function mountEconomics() {
  app = renderer.createApp({ setup(props, ctx) { state = EconomicsTab.setup({}, ctx); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.mount({})
  await flush()
}
beforeEach(() => {
  setActivePinia(createPinia()); store = usePricingStore()
  store.globalParams.payment_date = ''
  mocks.fetch.mockReset(); mocks.fetch.mockResolvedValue(response([]))
})
afterEach(() => { app?.unmount(); app = null })

describe('règlement final qualifié par le calendrier serveur', () => {
  it('laisse la date vide et affiche une erreur si le calendrier est indisponible', async () => {
    await mountEconomics()
    mocks.fetch.mockRejectedValue(new Error('Unavailable'))
    state.paymentDateDirty.value = false
    store.globalParams.payment_date = ''
    await state.proposePaymentDate('2026-04-02'); await flush()
    expect(store.globalParams.payment_date).toBe('')
    expect(state.paymentDateError.value).toContain('règlement non proposé')
  })

  it('utilise J+3 TARGET retourné par le serveur, y compris les fériés', async () => {
    await mountEconomics()
    mocks.fetch.mockResolvedValue(response({ date: '2026-04-09' }))
    state.paymentDateDirty.value = false
    await state.proposePaymentDate('2026-04-02'); await flush()
    expect(store.globalParams.payment_date).toBe('2026-04-09')
    expect(state.paymentDateError.value).toBe('')
    expect(JSON.parse(mocks.fetch.mock.lastCall[1].body)).toMatchObject({ business_days: 3, currency: 'EUR' })
  })

  it('préserve une date manuelle et un calendrier booké', async () => {
    store.globalParams.payment_date = '2026-04-10'
    await mountEconomics()
    mocks.fetch.mockClear()
    await state.proposePaymentDate('2026-04-02')
    expect(store.globalParams.payment_date).toBe('2026-04-10')
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('refuse toute proposition pour un contrat rouvert et conserve sa maturité figée', async () => {
    store.openedDeal = { id: 1 }
    store.currentProduct = { terms: { maturity_date: '2026-04-02' } }
    store.globalParams.payment_date = '2026-04-10'
    await mountEconomics(); mocks.fetch.mockClear()
    state.paymentDateDirty.value = false
    await state.proposePaymentDate('2026-05-02')
    expect(store.globalParams.payment_date).toBe('2026-04-10')
    expect(store.maturityDate).toBe('2026-04-02')
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('emploie les centres de règlement terminaux choisis dans Economics', async () => {
    await mountEconomics()
    store.scriptConstats = [{ name: 'OBS', kind: 'single' }]
    store.constatOverrides.OBS = { date: '2026-04-02', settlement_calendars: ['USD', 'TARGET'], settlement_join: 'all_open' }
    await flush(); mocks.fetch.mockClear()
    state.paymentDateDirty.value = false
    mocks.fetch.mockResolvedValue(response({ date: '2026-04-09' }))
    await state.proposePaymentDate('2026-04-02')
    expect(JSON.parse(mocks.fetch.mock.lastCall[1].body)).toMatchObject({ settlement_calendars: ['USD', 'TARGET'], settlement_join: 'all_open' })
  })

  it('ignore une réponse obsolète et efface la proposition automatique devenue périmée', async () => {
    await mountEconomics()
    state.paymentDateDirty.value = false
    let finishOld
    mocks.fetch.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
    const first = state.proposePaymentDate('2026-04-02')
    mocks.fetch.mockResolvedValueOnce(response({ date: '2026-05-07' }))
    await state.proposePaymentDate('2026-05-04')
    finishOld(response({ date: '2026-04-09' })); await first; await flush()
    expect(store.globalParams.payment_date).toBe('2026-05-07')
    mocks.fetch.mockResolvedValueOnce({ ok: false })
    await state.proposePaymentDate('2026-06-01'); await flush()
    expect(store.globalParams.payment_date).toBe('')
    expect(state.paymentDateError.value).toContain('Calendrier indisponible')
  })
})

describe('PARAM() et calendriers propres à chaque observation', () => {
  async function reopen(calendarStatus, frozenSchedule) {
    mocks.fetch.mockResolvedValue(response({ ok: true, params: [], constats: [{ name: 'OBS', kind: 'schedule' }], events_count: 1 }))
    await store.loadFromDeal({ id: 1, reference: 'C05', script_snapshot: 'CONSTAT() OBS\nAT OBS:\n  PAY 1',
      strike_date: '2026-01-31', value_date: '2026-02-02', maturity_date: '2026-05-31', payment_date: '2026-06-03', T: .33, devise: 'EUR',
      market_snapshot: { underlyings: [{ name: 'A', ticker: 'A', ccy: 'EUR', sigma: 20, q: 0 }],
        constats: { OBS: { start_date: '2026-01-31', end_date: '2026-05-31', roll_date: '2026-01-31', frequency: '1M' } } },
      calendar_status: calendarStatus, frozen_schedule: frozenSchedule })
  }
  it('transmet le calendrier de la version bookée au pricing et à la vie résiduelle', async () => {
    const frozen = { version: 1, events: [{ dates: [.2, .3] }], schedule: { constatations: [] } }
    await reopen('FROZEN', frozen)
    expect(store.pricingBody().frozen_schedule).toEqual(frozen)
    expect(store.inLifeBody().frozen_schedule).toEqual(frozen)
  })
  it('bloque le repricing si le serveur ne peut qualifier le calendrier figé', async () => {
    await reopen('UNAVAILABLE', null)
    expect(() => store.pricingBody()).toThrow('Calendrier contractuel figé indisponible')
    expect(() => store.inLifeBody()).toThrow('Calendrier contractuel figé indisponible')
  })
  it('le cache de maturité distingue les règles de combinaison', async () => {
    mocks.fetch.mockImplementation(async (url, options) => {
      const body = JSON.parse(options.body)
      return response({ date: body.observation_join === 'all_open' ? '2026-07-06' : '2026-07-03' })
    })
    store.scriptConstats = [{ name: 'OBS', kind: 'single' }]
    store.constatOverrides.OBS = { date: '2026-07-03', convention: 'following',
      observation_calendars: ['NYSE', 'XETR'], observation_join: 'all_open' }
    await flush()
    expect(store.maturityDate).toBe('2026-07-06')
    store.constatOverrides.OBS.observation_join = 'any_open'
    await flush()
    expect(store.maturityDate).toBe('2026-07-03')
    expect(mocks.fetch).toHaveBeenCalledTimes(2)
  })
  function setupPreview() {
    store = reactive({ scriptConstats: [{ name: 'CPN', kind: 'schedule' }, { name: 'CALL', kind: 'schedule' }],
      constatOverrides: Object.fromEntries(['CPN', 'CALL'].map(name => [name, {
        first_observation_date: '2027-01-31', end_date: '2027-10-31', frequency: { value: name === 'CPN' ? 3 : 12, unit: 'M' },
        observation_calendars: ['NYSE', 'XETR'], observation_join: 'any_open', settlement_calendars: ['TARGET'],
      }])), underlyings: [], result: null })
    app = renderer.createApp({ setup() { state = useObservationPreview(store, () => '2026-10-31', () => 'EUR'); return () => null } })
    app.mount({})
  }
  it('conserve les dates trimestrielles et annuelles séparément et transmet la règle choisie', async () => {
    mocks.fetch.mockImplementation(async (url, options) => {
      const body = JSON.parse(options.body)
      return response({ first_is_observation: true, dates: body.frequency === '3M' ? ['2027-01-31', '2027-04-30'] : ['2027-10-31'] })
    })
    setupPreview(); await flush()
    expect(state.datesByCalendar.value).toEqual({ CPN: ['2027-01-31', '2027-04-30'], CALL: ['2027-10-31'] })
    expect(state.datesObservations.value).toEqual(['2027-01-31', '2027-04-30', '2027-10-31'])
    expect(JSON.parse(mocks.fetch.mock.calls[0][1].body)).toMatchObject({ observation_join: 'any_open', settlement_calendars: ['TARGET'] })
  })

  it('retire les anciennes étiquettes lorsque le calendrier est refusé', async () => {
    mocks.fetch.mockResolvedValue(response({ first_is_observation: true, dates: ['2027-01-31'] }))
    setupPreview(); await flush()
    expect(state.datesByCalendar.value.CPN).toEqual(['2027-01-31'])
    mocks.fetch.mockResolvedValue({ ok: false })
    store.constatOverrides.CPN.observation_join = ''
    await flush()
    expect(state.datesByCalendar.value).toEqual({})
  })

  it('Economics étiquette un PARAM annuel à partir de son calendrier annuel', async () => {
    await mountEconomics()
    state.datesByCalendar.value = { QUARTER: ['2027-01-31'], YEAR: ['2027-10-31'] }
    expect(state.parameterDates({ observation_calendar: 'YEAR' })).toEqual(['2027-10-31'])
    expect(state.parameterDates({})).toEqual([])
  })

  it('affiche les dates historiques figées sans appeler le générateur C05', async () => {
    store = reactive({ contractTermsLocked: true, currentProduct: { terms: { schedule: { constatations: [
      { calendrier: 'OBS', rang: 1, date: '2026-02-28' }, { calendrier: 'OBS', rang: 2, date: '2026-03-28' },
    ] } } }, underlyings: [], result: null })
    app = renderer.createApp({ setup() { state = useObservationPreview(store, () => '2026-01-31', () => 'EUR'); return () => null } })
    app.mount({}); await flush()
    expect(state.datesByCalendar.value.OBS).toEqual(['2026-02-28', '2026-03-28'])
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('le tableau déplié lit le snapshot figé et conserve les dates de paiement', async () => {
    const frozenData = { dates: ['2026-02-28', '2026-03-28'], payment_dates: ['2026-03-04', '2026-04-01'] }
    app = renderer.createApp({ setup(props, ctx) {
      state = ObservationSchedule.setup({ request: {}, frozen: true, frozenData }, ctx); return () => null
    } })
    app.provide(ssrContextKey, { modules: new Set() }); app.mount({})
    await state.load()
    expect(state.data.value).toEqual(frozenData)
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('un ancien aperçu ne remplace pas le snapshot figé arrivé entre-temps', async () => {
    let finish
    mocks.fetch.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const props = reactive({ request: { first_observation_date: '2026-01-31', end_date: '2026-05-31', frequency: '1M' }, frozen: false })
    app = renderer.createApp({ setup(_, ctx) { state = ObservationSchedule.setup(props, ctx); return () => null } })
    app.provide(ssrContextKey, { modules: new Set() }); app.mount({})
    const pending = state.load()
    props.frozen = true; props.frozenData = { dates: ['2026-03-28'] }
    await flush(); await state.load()
    finish(response({ dates: ['2026-03-31'] })); await pending
    expect(state.data.value.dates).toEqual(['2026-03-28'])
  })
})

describe('choix contractuel de combinaison', () => {
  it('ne choisit aucune règle à la place du structureur et conserve les termes sérialisés', async () => {
    const values = reactive({ first_observation_date: '2027-01-31', end_date: '2028-01-31', frequency: { value: 1, unit: 'Y' } })
    mocks.fetch.mockResolvedValue(response({ observation_codes: ['NYSE', 'XETR'], settlement_codes: ['TARGET'] }))
    app = renderer.createApp({ setup(props, ctx) { state = CalendarPolicyFields.setup({ values, currency: 'EUR' }, ctx); return () => null } })
    app.provide(ssrContextKey, { modules: new Set() }); app.mount({}); await flush()
    state.selectCalendars('observation', { target: { selectedOptions: [{ value: 'NYSE' }, { value: 'XETR' }] } })
    expect(values.observation_join).toBe('')
    values.observation_join = 'all_open'
    values.settlement_calendars = ['TARGET']; values.settlement_join = 'all_open'
    const terms = serializeCalendars([{ name: 'OBS', kind: 'schedule' }], { OBS: values }, '2026-10-31')
    expect(terms.OBS).toMatchObject({ observation_calendars: ['NYSE', 'XETR'], observation_join: 'all_open', settlement_calendars: ['TARGET'] })
  })
})
