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
