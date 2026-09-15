import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useProductsStore } from './products.js'

function response(body, ok = true) {
  return { ok, json: async () => body }
}

describe('chargement des calculs conservés', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => vi.unstubAllGlobals())

  it('charge exactement le calcul demandé pour le reprendre', async () => {
    const product = {
      product_id: 12,
      revision: 4,
      terms_version: 2,
      calculations: [
        { id: 31, terms_version: 2 },
        { id: 32, terms_version: 2 },
      ],
    }
    const fetchMock = vi.fn(async url => {
      if (url === '/api/products/12') return response(product)
      if (url === '/api/products/12/calculations/31') {
        return response({ id: 31, input: { model: 'heston', valuation_date: '2026-09-12' } })
      }
      return response({}, false)
    })
    vi.stubGlobal('fetch', fetchMock)

    const loaded = await useProductsStore().fetchOne(12, { calculationId: 31 })

    expect(loaded.calculationId).toBe(31)
    expect(loaded.calculationInput).toEqual({
      model: 'heston', valuation_date: '2026-09-12',
    })
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      '/api/products/12',
      '/api/products/12/calculations/31',
    ])
  })

  it('refuse de mélanger un ancien calcul avec les termes courants', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      product_id: 12,
      revision: 5,
      terms_version: 3,
      calculations: [{ id: 30, terms_version: 2 }],
    })))
    const store = useProductsStore()

    const loaded = await store.fetchOne(12, { calculationId: 30 })

    expect(loaded).toBeNull()
    expect(store.error).toContain('ancienne version des termes')
  })

  it('déplie la fiche sans télécharger le détail de chaque résultat', async () => {
    const fetchMock = vi.fn(async () => response({
      product_id: 12,
      calculations: [{ id: 31, terms_version: 2 }],
    }))
    vi.stubGlobal('fetch', fetchMock)

    const product = await useProductsStore().fetchDetails(12)

    expect(product.calculations).toHaveLength(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/products/12', { headers: {} })
  })
})
