import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePortfoliosStore } from './portfolios.js'
import { useDealsStore } from './deals.js'

const response = (data, ok = true) => ({ ok, json: async () => data })
const settle = () => new Promise(resolve => setTimeout(resolve, 0))
function read(url) {
  const u = new URL(url, 'https://example.test')
  if (u.pathname === '/api/portfolios' || u.pathname === '/api/shocks' || u.pathname.endsWith('var-history')) return response([])
  return response({ data_scope: u.searchParams.get('data_scope'), marker: 'current' })
}

describe('périmètres des calculs et historiques de risque', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })
  afterEach(() => { usePortfoliosStore().stopVarPolling(); vi.unstubAllGlobals() })

  it('part de Production et sépare membres, risque et compteurs UAT', async () => {
    vi.stubGlobal('fetch', vi.fn(async url => read(url)))
    const store = usePortfoliosStore()
    useDealsStore().deals = [
      { id: 1, status: 'actif', nominal: 1e6, portfolio_ids: [9] },
      { id: 2, status: 'actif', nominal: 1e6, portfolio_ids: [9], uat_batch_id: 27 },
    ]
    expect(store.dataScope).toBe('PRODUCTION')
    expect(store.members.map(d => d.id)).toEqual([1])
    await store.setDataScope('UAT')
    expect(store.members.map(d => d.id)).toEqual([2])
    expect(store.activeDealsCount).toBe(1)
    expect(store.risk.data_scope).toBe('UAT')
    expect(store.scopeLabel).toBe('Recette UAT')
  })

  it('ignore une réponse Production tardive, même après un aller-retour UAT/Production', async () => {
    let deliver
    let first = true
    vi.stubGlobal('fetch', vi.fn(url => {
      if (url.includes('/risk-global') && first) {
        first = false
        return new Promise(resolve => { deliver = resolve })
      }
      return Promise.resolve(read(url))
    }))
    const store = usePortfoliosStore()
    const old = store.loadRisk()
    await store.setDataScope('UAT')
    await store.setDataScope('PRODUCTION')
    deliver(response({ marker: 'stale', data_scope: 'PRODUCTION' }))
    await old
    expect(store.risk.marker).toBe('current')
    expect(store.riskLoading).toBe(false)
  })

  it('transmet le même périmètre aux chocs, smile et P&L', async () => {
    const fetcher = vi.fn(async (url, options = {}) => options.method === 'POST'
      ? response({ data_scope: 'UAT' }) : read(url))
    vi.stubGlobal('fetch', fetcher)
    const store = usePortfoliosStore()
    await store.setDataScope('UAT')
    await store.runShock('global', null, { data_scope: 'PRODUCTION' })
    await store.runSmileRisk({})
    await store.runPnlExplain({})
    const posts = fetcher.mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(JSON.parse(posts[0][1].body).data_scope).toBe('UAT')
    expect(JSON.parse(posts[1][1].body).data_scope).toBe('UAT')
    expect(posts[2][0]).toContain('data_scope=UAT')
  })

  it('cloisonne les historiques de chocs et conserve une consultation legacy explicite', async () => {
    vi.stubGlobal('fetch', vi.fn(async url => url.startsWith('/api/shocks')
      ? response([{ id: url.includes('data_scope=UAT') ? 2 : url.includes('LEGACY_UNQUALIFIED') ? 3 : 1 }]) : read(url)))
    const store = usePortfoliosStore()
    await store.loadShockHistory('global', null)
    expect(store.currentShockHistory[0].id).toBe(1)
    await store.setDataScope('UAT')
    expect(store.currentShockHistory[0].id).toBe(2)
    await store.setHistoryMode('LEGACY_UNQUALIFIED')
    expect(store.currentShockHistory[0].id).toBe(3)
    expect(store.historyLabel).toBe('Historique non qualifié')
    expect(store.dataScope).toBe('UAT')
  })

  it('filtre les historiques VaR côté serveur par origine et portefeuille', async () => {
    const fetcher = vi.fn(async url => url.includes('var-history') ? response([{ id: 17 }]) : read(url))
    vi.stubGlobal('fetch', fetcher)
    const store = usePortfoliosStore()
    await store.selectView(9)
    await store.setDataScope('UAT')
    expect(store.varHistory).toEqual([{ id: 17 }])
    const requests = fetcher.mock.calls.map(([url]) => url)
    expect(requests).toContain('/api/portfolios/var-history?data_scope=UAT&scope=portfolio&portfolio_id=9')
    expect(requests.some(url => url.includes('/compute/batches'))).toBe(false)
  })

  it('arrête le polling et ignore son retour après un changement de périmètre', async () => {
    let deliver
    vi.stubGlobal('fetch', vi.fn(url => url === '/api/portfolios/var/10'
      ? new Promise(resolve => { deliver = resolve }) : Promise.resolve(read(url))))
    const store = usePortfoliosStore()
    store.openVarBatch(10)
    await store.setDataScope('UAT')
    deliver(response({ batch_id: 10, status: 'running', data_scope: 'PRODUCTION' }))
    await settle()
    expect(store.varStudy).toBeNull()
    expect(store.varPolling).toBe(false)
  })

  it('n’écrase pas le smile du nouveau périmètre avec une réponse ancienne', async () => {
    let deliver
    vi.stubGlobal('fetch', vi.fn((url, options = {}) => options.method === 'POST'
      ? new Promise(resolve => { deliver = resolve }) : Promise.resolve(read(url))))
    const store = usePortfoliosStore()
    const previous = store.runSmileRisk({})
    await store.setDataScope('UAT')
    deliver(response({ data_scope: 'PRODUCTION' }))
    expect(await previous).toBeNull()
    expect(store.smileResult).toBeNull()
  })

  it('préserve et étiquette les anciennes études du deal UAT sélectionné', async () => {
    const fetcher = vi.fn(async url => url.includes('LEGACY_UNQUALIFIED')
      ? response([{ id: 1, created_at: '2026-01-01', data_scope: 'LEGACY_UNQUALIFIED' }])
      : response([{ id: 2, created_at: '2026-02-01', data_scope: 'UAT' }]))
    vi.stubGlobal('fetch', fetcher)
    useDealsStore().deals = [{ id: 7, uat_batch_id: 27 }]
    const store = usePortfoliosStore()
    await store.loadShockHistory('deal', 7)
    expect(store.shockHistory[7].map(row => row.id)).toEqual([2, 1])
    expect(fetcher.mock.calls[0][0]).toContain('data_scope=UAT')
  })

  it('remonte un refus HTTP sans le publier comme total de risque', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ detail: 'Accès refusé' }, false)))
    const store = usePortfoliosStore()
    await expect(store.loadRisk()).rejects.toThrow('Accès refusé')
    expect(store.risk).toBeNull()
  })

  it('consulte les archives des portefeuilles supprimés sans changer le périmètre de calcul', async () => {
    const fetcher = vi.fn(async url => read(url))
    vi.stubGlobal('fetch', fetcher)
    const store = usePortfoliosStore()
    await store.setHistoryMode('ALL_VIEWS')
    expect(store.dataScope).toBe('PRODUCTION')
    expect(store.historyLabel).toBe('Production · toutes vues')
    expect(fetcher.mock.calls.some(([url]) => url.includes('var-history') && url.includes('all_views=true'))).toBe(true)
    expect(fetcher.mock.calls.some(([url]) => url.includes('/api/shocks') && url.includes('all_views=true'))).toBe(true)
  })
})
