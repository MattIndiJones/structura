import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from './api.js'
import { saveSession, clearSession, sessionToken } from './session.js'
import { destinationForContext } from './contextSwitch.js'
const bnp = { installation_id:'bnp', kind:'organization', url:'http://127.0.0.1:8101' }
const leonteq = { installation_id:'leonteq', kind:'organization', url:'http://127.0.0.1:8105' }
afterEach(() => { clearSession(); vi.unstubAllGlobals() })

describe('sessions par onglet et installation', () => {
  it('ignore les anciens jetons partagés et route le métier directement au service privé', async () => {
    localStorage.setItem('auth_token','old-shared')
    saveSession('bnp-token', bnp)
    const request = vi.fn(async () => ({ ok:true }))
    vi.stubGlobal('fetch', request)
    await apiFetch('/api/deals')
    expect(request.mock.calls[0][0]).toBe('http://127.0.0.1:8101/api/deals')
    expect(request.mock.calls[0][1].headers.Authorization).toBe('Bearer bnp-token')
    expect(localStorage.getItem('auth_token')).toBeNull()
    await expect(apiFetch('https://other.test/api/deals')).rejects.toThrow('Chemin API')
    expect(request).toHaveBeenCalledTimes(1)
  })
  it('ne remplace pas la session d’un autre onglet', () => {
    const first = sessionStorage
    saveSession('bnp-token', bnp)
    const values = new Map()
    vi.stubGlobal('sessionStorage', { getItem:k => values.get(k) || null, setItem:(k,v) => values.set(k,String(v)), removeItem:k => values.delete(k) })
    saveSession('leonteq-token', leonteq)
    expect(sessionToken()).toBe('leonteq-token')
    clearSession()
    expect(first.getItem('auth_token')).toBe('bnp-token')
  })
  it('annule et rejette une réponse tardive après une bascule', async () => {
    saveSession('bnp-token', bnp)
    let resolve
    const request = vi.fn(() => new Promise(done => { resolve = done }))
    vi.stubGlobal('fetch', request)
    const pending = apiFetch('/api/products')
    saveSession('leonteq-token', leonteq)
    expect(request.mock.calls[0][1].signal.aborted).toBe(true)
    resolve({ ok:true })
    await expect(pending).rejects.toMatchObject({ name:'AbortError' })
  })
})

describe('reprise du dossier au changement de profil', () => {
  const route = { path:'/products/12/pricer', fullPath:'/products/12/pricer', meta:{}, query:{} }
  const front = { role:'user', capabilities:['business.price'] }
  it('ne transporte jamais un identifiant local entre deux installations', async () => {
    const request = vi.fn()
    expect(await destinationForContext(route,bnp,leonteq,'token',front,request)).toBe('/')
    expect(request).not.toHaveBeenCalled()
  })
  it('reprend le dossier seulement après une autorisation serveur fraîche', async () => {
    const request = vi.fn(async () => ({ok:true}))
    expect(await destinationForContext(route,bnp,bnp,'front-token',front,request)).toBe(route.fullPath)
    expect(request.mock.calls[0][1].headers.Authorization).toBe('Bearer front-token')
    request.mockResolvedValue({ok:false})
    expect(await destinationForContext(route,bnp,bnp,'front-token',front,request)).toBe('/')
  })
  it('revient à l’accueil si le profil ne peut pas utiliser le Pricer', async () => {
    expect(await destinationForContext(route,bnp,bnp,'ops-token',{role:'ops_maker',capabilities:[]})).toBe('/')
  })
  it('ouvre la revue de booking après contrôle serveur du profil Opérations', async () => {
    const review = { path: '/rfq/12/booking', fullPath: '/rfq/12/booking', meta: { requiresBooking: true }, query: {} }
    const request = vi.fn(async () => ({ ok: true }))
    expect(await destinationForContext(review, bnp, bnp, 'ops-token', { role: 'ops_maker', capabilities: ['book'] }, request)).toBe(review.fullPath)
    expect(request.mock.calls[0][0]).toContain('/api/rfq/12/booking-review')
    expect(await destinationForContext(review, bnp, bnp, 'checker-token', { role: 'checker', capabilities: [] }, request)).toBe('/')
    expect(request).toHaveBeenCalledTimes(1)
  })
})
