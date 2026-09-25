import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { localDay, readMtmResponse, runTimestamp, useBookingMtm } from './useBookingMtm.js'

const reply = body => ({ ok: true, json: async () => body })
const saved = (changes = {}) => ({
  deal_id: 1, created_at: new Date().toISOString(),
  diagnostics: { request: { recalibrate: 'none' } },
  result: { mtm: 1.02, valuation_date: localDay() }, ...changes,
})
const deferred = () => {
  let resolve
  const promise = new Promise(r => { resolve = r })
  return { promise, resolve }
}

describe('MtM quotidien du Booking', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 8, 17, 12))
  })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

  it('ouvre sur les paramètres du booking et aujourd’hui, même si le dernier run est ancien', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reply([saved({
      created_at: new Date(2026, 8, 16, 12).toISOString(),
      diagnostics: { request: { recalibrate: 'none', valuation_date: '2026-09-16' } },
    })])))
    const state = useBookingMtm()
    await state.loadSavedMtm(1)
    expect(state.mtmModeFor(1)).toBe('booking')
    expect(state.mtmDateFor(1)).toBe('2026-09-17')
    expect(state.mtmResults[1]).toBeUndefined()
  })

  it.each([
    ['marché réalisé', () => ({ diagnostics: { request: { recalibrate: 'realized' } } })],
    ['date historique calculée aujourd’hui', () => ({ result: { mtm: 1, valuation_date: '2026-09-16' } })],
    ['timestamp absent', () => ({ created_at: null })],
    ['timestamp invalide', () => ({ created_at: 'invalid' })],
    ['surcharge', () => ({ diagnostics: { request: { recalibrate: 'none', r: 4 } } })],
    ['autre fenêtre', () => ({ diagnostics: { request: { recalibrate: 'none', window_days: 60 } } })],
  ])('ne restaure pas un run incompatible : %s', async (_, changes) => {
    vi.stubGlobal('fetch', vi.fn(async () => reply([saved(changes())])))
    const state = useBookingMtm()
    await state.loadSavedMtm(1)
    expect(state.mtmResults[1]).toBeUndefined()
  })

  it('restaure uniquement le résultat du jour et filtre les limites locales en UTC', async () => {
    const fetch = vi.fn(async () => reply([saved()]))
    vi.stubGlobal('fetch', fetch)
    const state = useBookingMtm()
    await state.loadSavedMtm(1)
    expect(state.mtmResults[1]).toMatchObject({ mtm: 1.02, _restored: true })
    const url = new URL(fetch.mock.calls[0][0], 'http://localhost')
    expect(new Date(url.searchParams.get('created_from')).getHours()).toBe(0)
    expect(url.searchParams.get('valuation_date')).toBe('2026-09-17')
    expect(url.searchParams.get('recalibrate')).toBe('none')
  })

  it('interprète les timestamps SQLite sans fuseau comme UTC', () => {
    expect(runTimestamp('2026-09-16T23:30:00').toISOString()).toBe('2026-09-16T23:30:00.000Z')
    expect(localDay(new Date(2026, 8, 17, 0, 1))).toBe('2026-09-17')
  })

  it('expire les résultats et remet les valeurs par défaut au changement de jour', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reply([saved()])))
    const state = useBookingMtm()
    await state.loadSavedMtm(1)
    state.setMtmMode(2, 'realized')
    state.setMtmDate(2, '2026-09-15')
    vi.setSystemTime(new Date(2026, 8, 18, 0, 0, 1))
    state.syncDay()
    expect(state.mtmResults[1]).toBeUndefined()
    expect(state.mtmModeFor(2)).toBe('booking')
    expect(state.mtmDateFor(2)).toBe('2026-09-18')
  })

  it('une restauration tardive ne remplace ni une sélection ni un nouveau calcul', async () => {
    const pending = deferred()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))
    const state = useBookingMtm()
    const restoration = state.loadSavedMtms([1, 2])
    state.setMtmMode(1, 'realized')
    state.setMtmMode(1, 'booking')
    state.setMtmDate(2, '2026-09-16')
    pending.resolve(reply([saved(), saved({ deal_id: 2 })]))
    await restoration
    expect(state.mtmResults[1]).toBeNull()
    expect(state.mtmResults[2]).toBeNull()
  })

  it('affiche le chargement immédiatement, bloque le double clic et transmet la sélection', async () => {
    const pending = deferred()
    const fetch = vi.fn(() => pending.promise)
    vi.stubGlobal('fetch', fetch)
    const state = useBookingMtm()
    const calculation = state.runMtm(1)
    expect(state.mtmLoading[1]).toBe(true)
    expect(state.mtmProgressLabel(1)).toContain('données de marché')
    state.setMtmMode(1, 'realized')
    await state.runMtm(1)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ recalibrate: 'none', valuation_date: '2026-09-17' })
    pending.resolve(reply({ mtm: 1.03 }))
    await calculation
    expect(state.mtmLoading[1]).toBe(false)
    expect(state.mtmResults[1].mtm).toBe(1.03)
  })

  it('ne passe en GBM réalisé que sur sélection explicite', async () => {
    const fetch = vi.fn(async () => reply({ mtm: 1.03 }))
    vi.stubGlobal('fetch', fetch)
    const state = useBookingMtm()
    state.setMtmMode(1, 'realized')
    await state.runMtm(1)
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ recalibrate: 'realized', valuation_date: '2026-09-17' })
  })

  it('ne réaffiche pas le calcul de la veille qui termine après minuit', async () => {
    const pending = deferred()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))
    const state = useBookingMtm()
    const calculation = state.runMtm(1)
    vi.setSystemTime(new Date(2026, 8, 18, 0, 1))
    pending.resolve(reply({ mtm: 1.03 }))
    await calculation
    expect(state.mtmResults[1]).toBeUndefined()
    expect(state.mtmDateFor(1)).toBe('2026-09-18')
  })
})

function streamResponse(parts) {
  return new Response(new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder()
      parts.forEach(part => controller.enqueue(encoder.encode(part)))
      controller.close()
    },
  }), { headers: { 'content-type': 'application/x-ndjson' } })
}

describe('progression réelle du calcul', () => {
  it('décode les messages fragmentés, puis le résultat', async () => {
    const progress = vi.fn()
    const result = await readMtmResponse(streamResponse([
      '{"type":"progress","phase":"calib', 'ration"}\n{"type":"progress","phase":"pricing"}\n',
      '{"type":"result","data":{"mtm":1.02}}\n',
    ]), progress)
    expect(progress.mock.calls).toEqual([['calibration'], ['pricing']])
    expect(result.mtm).toBe(1.02)
  })
  it('remonte l’échec de chargement sans inventer un résultat', async () => {
    await expect(readMtmResponse(streamResponse([
      '{"type":"error","detail":"Historique indisponible"}\n',
    ]), vi.fn())).rejects.toThrow('Historique indisponible')
  })
  it('signale un flux interrompu', async () => {
    await expect(readMtmResponse(streamResponse([
      '{"type":"progress","phase":"history"}\n',
    ]), vi.fn())).rejects.toThrow('interrompu')
  })
})
