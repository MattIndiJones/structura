import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useDealsStore } from './deals.js'

function response(body = []) {
  return { ok: true, json: async () => body }
}

describe('la watchlist reste le point d’entrée unique du Life Cycle', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => { vi.unstubAllGlobals() })

  it('garde l’appel produit autonome quand aucun client n’est demandé', async () => {
    const fetchMock = vi.fn(async () => response())
    vi.stubGlobal('fetch', fetchMock)

    await useDealsStore().getWatchlist()

    expect(fetchMock.mock.calls[0][0]).toBe('/api/deals/watchlist')
  })

  it('porte client et mandat dans la projection sans construire une autre API', async () => {
    const fetchMock = vi.fn(async () => response())
    vi.stubGlobal('fetch', fetchMock)

    await useDealsStore().getWatchlist({ clientId: 4, mandateId: 21 })

    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/deals/watchlist?client_id=4&mandate_id=21')
  })
})
