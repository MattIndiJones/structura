import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth.js'
import { tokenExpiry } from '../utils/session.js'

// A signed token's shape; only the claims matter to the tab.
function token(expSeconds, name = 'x') {
  const claims = btoa(JSON.stringify({ exp: Math.floor(expSeconds), sub: name })).replace(/=+$/, '')
  return `header.${claims.replace(/\+/g, '-').replace(/\//g, '_')}.signature`
}
const json = (data, status = 200) => ({ ok: status < 400, status, json: async () => data })
const identity = { role: 'user', username: 'front' }

beforeEach(() => { setActivePinia(createPinia()); sessionStorage.clear(); vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

it('lit l’échéance dans le jeton', () => {
  expect(tokenExpiry(token(1_800_000_000))).toBe(1_800_000_000_000)
  expect(tokenExpiry('pas-un-jeton')).toBeNull()
})

it('renouvelle le jeton cinq minutes avant son échéance, sans couper les requêtes en cours', async () => {
  const now = Date.now()
  const first = token(now / 1000 + 30 * 60, 'first'), second = token(now / 1000 + 60 * 60, 'second')
  const fetch = vi.fn(async () => json({ access_token: second }))
  vi.stubGlobal('fetch', fetch)
  const auth = useAuthStore()
  auth.activate(first, null, identity)
  await vi.advanceTimersByTimeAsync(24 * 60 * 1000)
  expect(fetch).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(60 * 1000 + 10)
  expect(fetch).toHaveBeenCalledOnce()
  const [url, options] = fetch.mock.calls[0]
  expect(url).toBe('/api/auth/refresh')
  expect(options.method).toBe('POST')
  expect(options.headers.Authorization).toBe(`Bearer ${first}`)
  expect(auth.token).toBe(second)
  expect(sessionStorage.getItem('auth_token')).toBe(second)
  expect(auth.user).toEqual(identity)                         // same session, same identity
})

it('la session de 12 heures écoulée ramène à la connexion avec le motif', async () => {
  const fetch = vi.fn(async () => json({ detail: 'Session de 12 heures écoulée : reconnectez-vous.' }, 401))
  vi.stubGlobal('fetch', fetch)
  const auth = useAuthStore()
  auth.activate(token(Date.now() / 1000 + 60), null, identity)
  await vi.advanceTimersByTimeAsync(2000)
  expect(auth.token).toBeNull()
  expect(sessionStorage.getItem('auth_token')).toBeNull()
  expect(sessionStorage.getItem('auth_notice')).toContain('12 heures')
})

it('un serveur injoignable n’efface pas la session et le renouvellement est retenté', async () => {
  const later = token(Date.now() / 1000 + 3600, 'later')
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch'))
    .mockResolvedValueOnce(json({ access_token: later }))
  vi.stubGlobal('fetch', fetch)
  const auth = useAuthStore()
  const first = token(Date.now() / 1000 + 60)
  auth.activate(first, null, identity)
  await vi.advanceTimersByTimeAsync(2000)
  expect(auth.token).toBe(first)
  await vi.advanceTimersByTimeAsync(30_000)
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(auth.token).toBe(later)
})

it('la déconnexion arrête le renouvellement', async () => {
  const fetch = vi.fn(async () => json({}))
  vi.stubGlobal('fetch', fetch)
  const auth = useAuthStore()
  auth.activate(token(Date.now() / 1000 + 6 * 60), null, identity)
  await auth.logout()
  fetch.mockClear()
  await vi.advanceTimersByTimeAsync(10 * 60 * 1000)
  expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/api/auth/refresh'))).toBe(false)
})

it('le portail de développement garde ses propres jetons', async () => {
  const fetch = vi.fn(async () => json({}))
  vi.stubGlobal('fetch', fetch)
  useAuthStore().activate(token(Date.now() / 1000 + 60), null, { role: 'platform_admin' })
  await vi.advanceTimersByTimeAsync(5 * 60 * 1000)
  expect(fetch).not.toHaveBeenCalled()
})
