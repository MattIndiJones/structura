import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useRfqStore } from './rfq.js'

function response(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }
}

describe('les mutations concurrentes d’une quote', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('reçoit un prix réseau en préservant les hypothèses locales et le dossier actif', async () => {
    const store = useRfqStore()
    store.current = { id: 1, name: 'Dossier privé', params: { r: 0.04 }, quotes: [] }
    vi.stubGlobal('fetch', vi.fn(async () => response({ id: 1, params: { r: 0.03 }, status: 'quote',
      business_status: 'QUOTING', selected_quote_id: null, quotes: [{ id: 9, origin: 'NETWORK', price: 98.5 }] })))
    await store.refreshNetworkQuotes(1)
    expect(store.current.quotes[0].price).toBe(98.5)
    expect(store.current.params.r).toBe(0.04)
    vi.stubGlobal('fetch', vi.fn(async () => response({ id: 1, quotes: [],
      execution_agreements: [{ id: 4, state: 'CONFIRMED' }], booked_deal: null })))
    await store.refreshNetworkQuotes(1)
    expect(store.current.execution_agreements[0].state).toBe('CONFIRMED')
    expect(store.current.params.r).toBe(0.04)
    let finish
    vi.stubGlobal('fetch', () => new Promise(resolve => { finish = resolve }))
    const pending = store.refreshNetworkQuotes(1)
    store.current = { id: 2, quotes: [] }
    finish(response({ id: 1, quotes: [{ id: 9, price: 99 }] }))
    await pending
    expect(store.current.id).toBe(2)
    expect(store.current.quotes).toEqual([])
  })

  it('envoie le statut après le prix et conserve les deux', async () => {
    let releasePrice
    const pricePending = new Promise(resolve => { releasePrice = resolve })
    const calls = []
    const server = { id: 4, price: null, status: 'en_attente' }
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => {
      const patch = JSON.parse(options.body)
      calls.push(patch)
      if ('price' in patch) await pricePending
      Object.assign(server, patch)
      return response({ ...server })
    }))

    const store = useRfqStore()
    store.current = { id: 2, quotes: [{ ...server }] }
    const price = store.updateQuote(2, 4, { price: 98.5 })
    const status = store.updateQuote(2, 4, { status: 'recu' })
    await vi.waitFor(() => expect(calls).toEqual([{ price: 98.5 }]))

    releasePrice()
    await Promise.all([price, status])
    expect(calls).toEqual([{ price: 98.5 }, { status: 'recu' }])
    expect(store.current.quotes[0]).toMatchObject({ price: 98.5, status: 'recu' })
  })
})

describe('le pricing daté d’une RFQ', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('passe par le pricing in-life pour un strike historique', async () => {
    const calls = []
    vi.stubGlobal('fetch', vi.fn(async (url, options) => {
      calls.push({ url, body: JSON.parse(options.body) })
      if (url === '/api/price/in-life') {
        return response({ price: 0.92, flux_table: {}, pre_strike: false })
      }
      return response({ id: 7, model_price: 92, params: {}, quotes: [] })
    }))

    const store = useRfqStore()
    await store.computeModelPrice({
      id: 7,
      ao_date: '2026-09-15',
      script_snapshot: 'AT MATURITY:\n  PAY 1',
      params: {
        strike_date: '2025-09-15',
        value_date: '2025-09-17',
        maturity_date: '2028-09-15',
        payment_date: '2028-09-18',
        T: 3,
        underlyings: [{ name: 'LVMH', ticker: 'MC.PA', ccy: 'EUR', sigma: 0.2, q: 0 }],
        corr_matrix: [[1]],
      },
    })

    expect(calls[0].url).toBe('/api/price/in-life')
    expect(calls[0].body).toMatchObject({
      valuation_date: new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10),
      strike_date: '2025-09-15',
      maturity_date: '2028-09-15',
    })
    expect(calls[1].body).toEqual({ model_price: 92 })
  })

  it('n’enregistre aucun faux prix quand le produit a déjà été rappelé', async () => {
    const fetchMock = vi.fn(async () => response({
      early_recall: true,
      recall_date: '2026-03-09',
      message: 'Produit rappelé à la première observation.',
    }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useRfqStore()

    await expect(store.computeModelPrice({
      id: 8,
      ao_date: '2026-09-15',
      script_snapshot: 'AT MATURITY:\n  PAY 1',
      params: {
        strike_date: '2025-09-15', maturity_date: '2028-09-15', T: 3,
        underlyings: [{ name: 'LVMH', ticker: 'MC.PA', ccy: 'EUR', sigma: 0.2, q: 0 }],
        corr_matrix: [[1]],
      },
    })).rejects.toThrow('Produit rappelé')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('price séparément chaque sous-jacent et conserve la matrice du panier', async () => {
    const calls = []
    vi.stubGlobal('fetch', vi.fn(async (url, options) => {
      calls.push({ url, body: JSON.parse(options.body) })
      if (url === '/api/price') return response({ price: 0.965, flux_table: {} })
      return response({ id: 9, model_price: 96.5, params: {}, quotes: [] })
    }))
    const store = useRfqStore()
    const basket = [
      { name: 'LVMH', ticker: 'MC.PA', ccy: 'EUR', sigma: 0.21, q: 0.018 },
      { name: 'DAX', ticker: '^GDAXI', ccy: 'EUR', sigma: 0.27, q: 0.031 },
    ]

    await store.computeModelPrice({
      id: 9,
      ao_date: '2026-09-15',
      script_snapshot: 'AT MATURITY:\n  PAY WOF',
      params: {
        valuation_date: '2026-09-15', strike_date: '2026-09-15', value_date: '2026-09-17',
        maturity_date: '2029-09-15', payment_date: '2029-09-18', T: 3,
        underlyings: basket, corr_matrix: [[1, 0.45], [0.45, 1]],
      },
    })

    expect(calls[0].url).toBe('/api/price')
    expect(calls[0].body.underlyings).toEqual(basket)
    expect(calls[0].body.corr_matrix).toEqual([[1, 0.45], [0.45, 1]])
    expect(store.lastPricing.hypotheses.underlyings).toEqual([
      { name: 'LVMH', ticker: 'MC.PA', sigma: 0.21, q: 0.018 },
      { name: 'DAX', ticker: '^GDAXI', sigma: 0.27, q: 0.031 },
    ])
    expect(store.lastPricing.hypotheses.corr_matrix).toEqual([[1, 0.45], [0.45, 1]])
  })
})

describe('RFQ et Product canonique', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })
  afterEach(() => vi.unstubAllGlobals())
  const rfq = { id: 7, product_id: 4, product_terms_version: 1, script_snapshot: 'projection locale périmée',
    params: { valuation_date: '2026-09-15', strike_date: '2026-09-15', underlyings: [{ name: 'Local', ccy: 'EUR', sigma: 0.99 }] } }
  const canonical = { product_id: 4, terms_version: 1, input_hash: 'a'.repeat(64), pricing_input: {
    script: 'AT MATURITY:\n  PAY 1', strike_date: '2026-09-12', value_date: '2026-09-17',
    maturity_date: '2029-09-12', payment_date: '2029-09-17', valuation_date: '2026-09-15',
    underlyings: [{ name: 'Canonical', ticker: 'MC.PA', ccy: 'EUR', sigma: 0.3, q: 0.02 }],
    corr_matrix: [[1]], r: 0.02, N: 1000, model: 'constant', frozen_schedule: { events: [] },
  } }
  it('compose depuis Product puis appelle le moteur daté existant avec ses hypothèses effectives', async () => {
    const calls = []
    vi.stubGlobal('fetch', vi.fn(async (url, options) => {
      calls.push({ url, body: JSON.parse(options.body) })
      if (url.endsWith('/pricing-input')) return response(structuredClone(canonical))
      if (url === '/api/price/in-life') return response({ price: 0.972, flux_table: {} })
      return response({ id: 7, model_price: 97.2 })
    }))
    const store = useRfqStore()
    await store.computeModelPrice(rfq)
    expect(calls.map(call => call.url)).toEqual(['/api/rfq/7/pricing-input', '/api/price/in-life', '/api/rfq/7'])
    expect(calls[0].body).toEqual({ expected_terms_version: 1, valuation_date: '2026-09-15' })
    expect(calls[1].body).toEqual(canonical.pricing_input)
    expect(calls[2].body).toEqual({ model_price: 97.2, expected_model_input_hash: canonical.input_hash })
    expect(store.lastPricing.hypotheses.underlyings[0]).toMatchObject({ name: 'Canonical', sigma: 0.3 })
    expect(store.lastPricing.strikeDate).toBe('2026-09-12')
  })
  it('ne lance pas le moteur ni un repli local si la version est refusée', async () => {
    const fetch = vi.fn(async () => response({ detail: { message: 'Termes périmés' } }, 409))
    vi.stubGlobal('fetch', fetch)
    await expect(useRfqStore().computeModelPrice(rfq)).rejects.toThrow('Termes périmés')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('ne présente pas un calcul comme enregistré si les hypothèses ont changé pendant le calcul', async () => {
    vi.stubGlobal('fetch', vi.fn(async url => url.endsWith('/pricing-input') ? response(structuredClone(canonical))
      : url === '/api/price/in-life' ? response({ price: 0.972 }) : response({ detail: 'Hypothèses modifiées' }, 409)))
    const store = useRfqStore()
    await expect(store.computeModelPrice(rfq)).rejects.toThrow('Hypothèses modifiées')
    expect(store.lastPricing).toBeNull()
  })
  it('prépare une projection sans ajouter de cotation ni changer le dossier', async () => {
    const packet = { request: { terms_version: 1 }, messages: [], delivery_available: false }
    const calls = []
    vi.stubGlobal('fetch', vi.fn(async (url, options) => { calls.push({ url, body: JSON.parse(options.body) }); return response(packet) }))
    const store = useRfqStore()
    store.current = { ...rfq, quotes: [], status: 'draft' }
    const before = JSON.stringify(store.current)
    expect(await store.previewExchange(rfq, { sharedTitle: 'Athena', deadline: '2026-10-12T14:00:00Z', providerIds: [2] })).toEqual(packet)
    expect(calls).toEqual([{ url: '/api/rfq/7/exchange-preview', body: { expected_terms_version: 1, shared_title: 'Athena', response_deadline: '2026-10-12T14:00:00Z', provider_ids: [2] } }])
    expect(JSON.stringify(store.current)).toBe(before)
  })
  it('utilise les relations autorisées et distingue leurs identifiants des fournisseurs manuels', async () => {
    const calls = []
    vi.stubGlobal('fetch', vi.fn(async (url, options) => {
      calls.push({ url, body: options?.body ? JSON.parse(options.body) : null })
      return response(url.endsWith('/recipients') ? { eligible: [{ id: 9, label: 'BNP' }], excluded: [] } : { messages: [], delivery_available: false })
    }))
    const store = useRfqStore()
    expect((await store.fetchRecipients(7)).eligible[0].id).toBe(9)
    await store.previewExchange(rfq, { sharedTitle: 'Athena', deadline: '2026-10-12T14:00:00Z', relationshipIds: [9], providerIds: [2] })
    expect(calls[1].body.relationship_ids).toEqual([9])
    expect(calls[1].body.provider_ids).toEqual([2])
  })
})
