import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join, relative } from 'node:path'
import { apiFetch } from './api.js'

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('authentification des appels API', () => {
  it('relit le jeton à chaque appel et conserve les options JSON et multipart', async () => {
    const fetch = vi.fn(async () => ({ ok: true }))
    vi.stubGlobal('fetch', fetch)
    localStorage.setItem('auth_token', 'first-session')
    await apiFetch('/api/parse', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    })
    expect(fetch.mock.calls[0][1]).toEqual({
      method: 'POST', body: '{}',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer first-session' },
    })
    localStorage.setItem('auth_token', 'renewed-session')
    const form = new FormData()
    await apiFetch('/api/script/transcribe', { method: 'POST', body: form })
    expect(fetch.mock.calls[1][1]).toEqual({
      method: 'POST', body: form, headers: { Authorization: 'Bearer renewed-session' },
    })
  })

  it('ne laisse aucun écran métier contourner le transport authentifié', () => {
    // A raw fetch silently broke pricing when server authentication was enabled.
    // Login/register and the auth store have their own explicit auth contract.
    const root = fileURLToPath(new URL('../', import.meta.url))
    const allowed = new Set(['utils/api.js', 'stores/auth.js', 'views/LoginView.vue'])
    const offenders = []
    function inspect(directory) {
      for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const path = join(directory, entry.name)
        if (entry.isDirectory()) { inspect(path); continue }
        const name = relative(root, path).replaceAll('\\', '/')
        if (!/\.(js|vue)$/.test(name) || name.endsWith('.test.js') || allowed.has(name)) continue
        if (/\bfetch\s*\(/.test(readFileSync(path, 'utf8'))) offenders.push(name)
      }
    }
    inspect(root)
    expect(offenders).toEqual([])
  })
})
