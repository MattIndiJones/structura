import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join, relative } from 'node:path'
import { apiFetch, apiErrorMessage } from './api.js'

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('messages de validation API lisibles', () => {
  it('traduit les dates et nombres absents sans afficher le JSON ni doubler StartDate', () => {
    const message = apiErrorMessage({ detail: [
      { type: 'float_type', loc: ['body', 'T'], input: null, msg: 'Input should be a valid number' },
      { type: 'date_from_datetime_parsing', loc: ['body', 'anchor'], input: '' },
      { type: 'date_from_datetime_parsing', loc: ['body', 'strike_date'], input: '' },
    ] })
    expect(message).toBe('Durée entre StartDate et maturité : à renseigner.\nStartDate / date de strike : à renseigner.')
  })

  it('identifie le sous-jacent et la contrainte de cours initial', () => {
    expect(apiErrorMessage({ detail: [{
      type: 'greater_than', loc: ['body', 'underlyings', 1, 'spot0'], input: -50, ctx: { gt: 0 },
    }] })).toBe('Sous-jacent 2 — Cours initial en devise : la valeur doit être supérieure à 0.')
  })

  it('préserve le message métier du serveur et traite les formes inconnues', () => {
    expect(apiErrorMessage({ detail: 'La première observation doit suivre StartDate.' })).toBe('La première observation doit suivre StartDate.')
    expect(apiErrorMessage({ detail: { message: 'Cours indisponible.' } })).toBe('Cours indisponible.')
    expect(apiErrorMessage({ detail: { unexpected: 3 } }, 'Calcul impossible.')).toBe('Calcul impossible.')
    expect(apiErrorMessage({ detail: [{ loc: ['body', 'x'], type: 'unknown', input: 2 }] })).toBe('Une valeur saisie : valeur invalide, à corriger.')
  })
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
