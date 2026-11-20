import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../utils/api.js', async () => {
  const actual = await vi.importActual('../utils/api.js')
  return { ...actual, apiFetch: (...args) => mocks.api(...args) }
})
import { ApiError, getDeal, histPrices, listDeals, resolveBusinessDay } from './generated.js'

const reply = (body, status = 200) => ({ ok: status < 400, status, json: async () => body })
beforeEach(() => mocks.api.mockReset())

describe('client généré depuis les contrats du serveur', () => {
  it('appelle la route publiée et rend le corps', async () => {
    mocks.api.mockResolvedValueOnce(reply([{ id: 1, reference: 'DEMO-1' }]))
    expect(await listDeals()).toEqual([{ id: 1, reference: 'DEMO-1' }])
    expect(mocks.api).toHaveBeenCalledWith('/api/deals', { method: 'GET' })
  })
  it('encode les paramètres de chemin', async () => {
    mocks.api.mockResolvedValueOnce(reply({ id: 7 }))
    await getDeal('7/../8')
    expect(mocks.api.mock.calls[0][0]).toBe('/api/deals/7%2F..%2F8')
  })
  it('n’envoie que les paramètres de requête renseignés', async () => {
    mocks.api.mockResolvedValueOnce(reply({ dates: [] }))
    await histPrices({ tickers: 'AIR.PA,SAN.PA', start: '2026-01-01', end: undefined })
    expect(mocks.api.mock.calls[0][0]).toBe('/api/finance/hist_prices?tickers=AIR.PA%2CSAN.PA&start=2026-01-01')
  })
  it('envoie le corps en JSON', async () => {
    mocks.api.mockResolvedValueOnce(reply({ date: '2026-11-20' }))
    await resolveBusinessDay({ date: '2026-11-21', currency: 'EUR' })
    const [, init] = mocks.api.mock.calls[0]
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse(init.body)).toEqual({ date: '2026-11-21', currency: 'EUR' })
  })
  it('un refus devient une ApiError avec le message du serveur', async () => {
    mocks.api.mockResolvedValueOnce(reply({ detail: 'Deal introuvable' }, 404))
    const error = await getDeal(9).catch(e => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toBe('Deal introuvable')
    expect(error.status).toBe(404)
    expect(error.body).toEqual({ detail: 'Deal introuvable' })
  })
  it('un corps illisible ne masque pas le statut', async () => {
    mocks.api.mockResolvedValueOnce({ ok: false, status: 502, json: async () => { throw new Error('html') } })
    const error = await listDeals().catch(e => e)
    expect(error.status).toBe(502)
    expect(error.message).toBe('Erreur 502')
  })
})
