import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, h, nextTick, reactive, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import DealTab from './DealTab.vue'
import { usePricingStore } from '../stores/pricing.js'

const mocks = vi.hoisted(() => ({ auth: null, book: vi.fn(), fetch: vi.fn() }))
vi.mock('../stores/auth.js', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('../stores/deals.js', () => ({ useDealsStore: () => ({ bookDeal: mocks.book }) }))
vi.mock('../utils/api.js', () => ({ apiFetch: (...args) => mocks.fetch(...args) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), RouterLink: {} }))
const renderer = createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
let app, state, store

async function mount() {
  setActivePinia(createPinia())
  store = usePricingStore()
  app = renderer.createApp({ setup(props, ctx) { state = DealTab.setup(props, ctx); return () => null } })
  app.provide(ssrContextKey, { modules: new Set() }); app.mount({})
  for (let i = 0; i < 5; i++) await nextTick()
}
function authorize() {
  state.legalException.enabled = true
  state.form.contrepartie = 'Banque Nouvelle SA'
  state.legalException.reason = 'Dossier juridique vérifié par l’administrateur'
}
function prepareReview() {
  Object.assign(store.globalParams, { nominal: 1000000, strike_date: '2026-10-20', value_date: '2026-10-20',
    payment_date: '2027-10-25', T: 1 })
  store.maturityDate = '2027-10-20'
  state.form.fair_value = 100; state.form.price_traded = 99; state.form.payoff_family = 'Autocall'
  state.reviewSnapshot.value = state.marketSnapshotForBooking()
  state.reviewSnapshotJson.value = JSON.stringify(state.reviewSnapshot.value)
}
beforeEach(() => {
  mocks.auth = reactive({ user: { id: 7 }, canAdministerOrganization: true, canBook: true })
  mocks.book.mockReset(); mocks.fetch.mockReset()
  mocks.fetch.mockResolvedValue({ ok: true, json: async () => [] })
})
afterEach(() => app?.unmount())

describe('exception juridique au booking', () => {
  it('exige une autorisation explicite et conserve le refus sans identifiant par défaut', async () => {
    await mount()
    expect(state.legalException.enabled).toBe(false)
    state.validate()
    expect(state.errors.contrepartie).toContain('active requise')
    state.legalException.enabled = true
    state.validate()
    expect(state.errors.legal_exception).toContain('Motivez')
    expect(state.errors.contrepartie).toContain('Nom juridique requis')
    authorize(); state.validate()
    expect(state.errors.legal_exception).toBeUndefined()
    expect(state.errors.contrepartie).toBeUndefined()
  })

  it('efface le netting set et la banque sélectionnée avant l’exception', async () => {
    await mount()
    state.form.counterparty_id = 1; state.form.contrepartie = 'Banque connue'
    state.ccrNettingSetId.value = 12
    authorize()
    expect(state.form.counterparty_id).toBeNull()
    expect(state.ccrNettingSetId.value).toBeNull()
    state.legalException.enabled = false
    expect(state.form.contrepartie).toBe('')
    expect(state.legalException.reason).toBe('')
  })

  it.each(['rfq', 'note', 'user', 'product', 'role'])('efface une autorisation lors du changement de contexte %s', async context => {
    await mount(); authorize()
    if (context === 'rfq') store.currentRfqId = 22
    if (context === 'note') state.noteExecution.enabled = true
    if (context === 'user') mocks.auth.user.id = 8
    if (context === 'product') store.currentProduct = { product_id: 23 }
    if (context === 'role') mocks.auth.canAdministerOrganization = false
    expect(state.legalException.enabled).toBe(false)
    expect(state.legalException.reason).toBe('')
  })

  it('refuse une tentative de soumission par un profil non administrateur', async () => {
    mocks.auth.canAdministerOrganization = false
    await mount(); authorize(); state.validate()
    expect(state.errors.legal_exception).toContain('réservée')
    prepareReview()
    await state.book()
    expect(state.errors.legal_exception).toContain('réservée')
    expect(mocks.book).not.toHaveBeenCalled()
  })

  it('transmet l’exception et le motif, puis conserve la contrepartie du booking confirmé', async () => {
    await mount(); authorize()
    // The review must retain the same pricing inputs until confirmation.
    prepareReview()
    mocks.book.mockImplementation(async payload => ({ id: 4, ...payload }))
    await state.book()
    expect(mocks.book).toHaveBeenCalledOnce()
    expect(mocks.book.mock.calls[0][0]).toMatchObject({ counterparty_id: null, ccr_netting_set_id: null,
      contrepartie: 'Banque Nouvelle SA', legal_identity_exception: { reason: 'Dossier juridique vérifié par l’administrateur' } })
    expect(state.legalException.enabled).toBe(false)
    expect(state.form.contrepartie).toBe('Banque Nouvelle SA')
  })
})

describe('autre opération et filiation', () => {
  function origin() {
    store.currentProduct = { product_id: 12, revision: 5, terms_version: 2,
      execution: { deal_id: 4 }, rfqs: [{ id: 3 }], indicatives: [{ id: 2 }] }
    store.openedDeal = { id: 4, product_id: 12 }
    store.currentRfqId = 3; store.currentIndicativeId = 2
    store.currentRfqExecution = { agreement: { id: 1, state: 'CONFIRMED' } }
    store.result = { price: 1, pricing_receipt: { signature_version: 2 } }
    Object.assign(state.form, { client_id: 8, mandate_id: 9, opportunity_id: 10, primary_affiliation_id: 11 })
  }
  const child = { product_id: 13, origin_product_id: 12, revision: 1, terms_version: 1,
    execution: null, rfqs: [], indicatives: [], terms: {} }

  it('crée un dossier relié puis détache les anciennes preuves et le contexte commercial', async () => {
    await mount(); origin()
    mocks.fetch.mockResolvedValue({ ok: true, json: async () => child })
    await state.rearmBooking()
    expect(store.currentProduct).toMatchObject(child)
    expect(store.openedDeal).toBeNull(); expect(store.result).toBeNull()
    expect(store.currentRfqId).toBeNull(); expect(store.currentIndicativeId).toBeNull()
    expect(store.currentRfqExecution).toBeNull()
    expect(state.form.client_id).toBeNull(); expect(state.form.opportunity_id).toBeNull()
    expect(store.productLoadNotice).toContain('relancez le prix')
    expect(state.form.fair_value).toBe(0)
    store.result = { price: 0.985 }
    await nextTick()
    expect(state.form.fair_value).toBe(98.5)
  })

  it('garde le dossier exécuté après un échec et reprend la même commande de filiation', async () => {
    await mount(); origin()
    const posted = []
    mocks.fetch.mockImplementation(async (_url, options) => {
      posted.push(JSON.parse(options.body))
      if (posted.length === 1) throw new Error('Réponse perdue')
      return { ok: true, json: async () => child }
    })
    await state.rearmBooking()
    expect(store.currentProduct.product_id).toBe(12)
    expect(store.openedDeal.id).toBe(4)
    expect(state.bookingError.value).toBe('Réponse perdue')
    await state.rearmBooking()
    expect(posted[1].command_key).toBe(posted[0].command_key)
    expect(store.currentProduct.product_id).toBe(13)
  })

  it('ne remplace pas une autre session ouverte pendant la préparation', async () => {
    await mount(); origin()
    let finish, started
    const ready = new Promise(resolve => { started = resolve })
    mocks.fetch.mockImplementation(async () => { started(); return new Promise(resolve => { finish = resolve }) })
    const pending = state.rearmBooking()
    await ready
    store.currentProduct = { product_id: 99 }
    store.openedDeal = { id: 98, product_id: 99 }
    finish({ ok: true, json: async () => child })
    await pending
    expect(store.currentProduct.product_id).toBe(99)
    expect(store.openedDeal.id).toBe(98)
  })
})

describe('première exécution d’un Product conservé', () => {
  const product = { product_id: 21, reference: 'PRD-BANK-21', revision: 2, terms_version: 1,
    terms: { script: 'AT 1:\n  PAY 1\n', underlyings: [], T: 1, constats: {}, parameters: [] },
    intent: { side: 'SELL', nominal: 1000000, transaction_format: 'EMTN', instrument_family: 'Note',
      payoff_family: 'Autocall', documentation_reference: 'TERM-SHEET-21' }, commercial: {} }

  it('reprend le sens bancaire et la documentation sans réutiliser l’exécution du dossier précédent', async () => {
    await mount()
    state.form.price_traded = 99; state.form.counterparty_id = 10
    Object.assign(state.noteExecution, { enabled: true, trade_reference: 'OLD-TRADE', relationship_id: 7 })
    mocks.fetch.mockResolvedValue({ ok: true, json: async () => ({ ok: true, params: [], constats: [] }) })
    await store.loadFromProduct(product)
    await nextTick()
    expect(state.form).toMatchObject({ sens: 'achat', counterparty_id: null, contrepartie: '',
      transaction_format: 'EMTN', instrument_family: 'Note', payoff_family: 'Autocall',
      documentation_reference: 'TERM-SHEET-21', price_traded: 0, fair_value: 0 })
    expect(state.noteExecution).toMatchObject({ enabled: false, relationship_id: null, trade_reference: '' })
    expect(store.globalParams.nominal).toBe(1000000)
    expect(store.contractTermsLocked).toBe(true)
    expect(state.existingDeal.value).toBeNull()
  })

  it('laisse compléter l’exécution et la contrepartie manquante tout en figeant les termes du Product', async () => {
    setActivePinia(createPinia())
    usePricingStore().currentProduct = product
    const ssr = createSSRApp({ render: () => h(DealTab) })
    const html = (await renderToString(ssr)).replace(/<!--[\s\S]*?-->/g, '')
    const sections = html.match(/<fieldset class="card"[^>]*>/g)
    expect(sections).toHaveLength(2)
    expect(sections.every(section => !section.includes('disabled'))).toBe(true)
    expect(html).toMatch(/<select class="select">/)
    expect(html).toMatch(/<button disabled[^>]*>[^<]*↓ Achat/)
    expect(html).toMatch(/<input[^>]*list="deal-formats"[^>]*disabled/)
    expect(html).toContain('Inscrire une exécution de note dans le journal des relations')
  })

  it('reconnaît le deal déjà booké à la réouverture et ne propose pas un second booking', async () => {
    await mount()
    store.currentProduct = { ...product, execution: { deal_id: 42, reference: 'DEAL-42', fair_value: 94.1256, price_traded: 98.5 } }
    expect(state.existingDeal.value).toMatchObject({ id: 42, reference: 'DEAL-42' })
  })
})
