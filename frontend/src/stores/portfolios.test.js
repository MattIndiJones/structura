import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { usePortfoliosStore } from './portfolios.js'

function response(body = {}, ok = true) {
  return { ok, json: async () => body }
}

describe('gestion des portefeuilles', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => { vi.unstubAllGlobals() })

  it('remonte explicitement une assignation refusée par l’API', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      response({ detail: 'Portefeuille introuvable' }, false)))

    await expect(usePortfoliosStore().assignDeal(12, '99'))
      .rejects.toThrow('Portefeuille introuvable')
  })

  it('permet à l’admin de créer un portefeuille pour le compte sélectionné', async () => {
    const fetchMock = vi.fn(async (url, options = {}) => {
      if (url === '/api/portfolios' && options.method === 'POST') {
        return response({ id: 7, name: 'Book test', user_id: 2, owner_username: 'test' })
      }
      if (url === '/api/portfolios') {
        return response([{ id: 7, name: 'Book test', user_id: 2, owner_username: 'test' }])
      }
      throw new Error(`Appel inattendu : ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const created = await usePortfoliosStore().create('Book test', 2)

    expect(created.user_id).toBe(2)
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ name: 'Book test', user_id: 2 })
  })

  it('conserve plusieurs appartenances puis recharge les deals et les compteurs', async () => {
    const fetchMock = vi.fn(async (url, options = {}) => {
      if (url === '/api/deals/12/portfolios' && options.method === 'PUT') {
        expect(JSON.parse(options.body)).toEqual({ portfolio_ids: [2, 3] })
        return response({ id: 12, portfolio_ids: [2, 3] })
      }
      if (url === '/api/deals') return response([{ id: 12, portfolio_ids: [2, 3], status: 'actif' }])
      if (url === '/api/portfolios') {
        return response([{ id: 3, name: 'Mandat EUR', is_default: false, deal_count: 1 }])
      }
      throw new Error(`Appel inattendu : ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const assigned = await usePortfoliosStore().setDealPortfolios(12, [2, 3])

    expect(assigned).toEqual({ id: 12, portfolio_ids: [2, 3] })
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      '/api/deals/12/portfolios', '/api/deals', '/api/portfolios',
    ])
  })
})
