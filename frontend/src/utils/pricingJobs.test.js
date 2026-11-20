import { afterEach, describe, expect, it, vi } from 'vitest'

// The setup file replaces this module for the store's tests: test the real one.
const { runQueuedCalculation, cancelQueuedCalculation } = await vi.importActual('./pricingJobs.js')

function reply(body, ok = true) {
  return { ok, json: async () => body }
}

/** A server whose job answers `states` in turn, then stays on the last one. */
function server(states, { submitted = { job_id: 'j1', status: 'queued', queue_position: 1 } } = {}) {
  const calls = []
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
    calls.push([String(url), options.method || 'GET', options.body])
    if ((options.method || 'GET') === 'POST') return reply(submitted, !submitted.detail)
    if (options.method === 'DELETE') return reply({ status: 'cancelled' })
    return reply(states.length > 1 ? states.shift() : states[0])
  }))
  return calls
}

const fast = { firstDelay: 1, maxDelay: 2 }

afterEach(() => vi.unstubAllGlobals())

describe('file de calcul interactive', () => {
  it('dépose le calcul sur la route de file et rend son résultat', async () => {
    const calls = server([{ status: 'running', elapsed_ms: 40 }, { status: 'done', result: { price: 0.987 } }])
    const seen = []
    const out = await runQueuedCalculation('/api/price', { N: 2000 }, { ...fast, onState: s => seen.push(s.status) })
    expect(out).toEqual({ ok: true, data: { price: 0.987 } })
    expect(calls[0]).toEqual(['/api/price/jobs/price', 'POST', JSON.stringify({ N: 2000 })])
    expect(calls.slice(1).every(([url, method]) => url === '/api/price/jobs/j1' && method === 'GET')).toBe(true)
    expect(seen).toEqual(['queued', 'running', 'done'])
  })

  it('route la valorisation en cours de vie et le spread implicite', async () => {
    const calls = server([{ status: 'done', result: {} }])
    await runQueuedCalculation('/api/price/in-life', {}, fast)
    await runQueuedCalculation('/api/price/implied-funding', {}, fast)
    const posts = calls.filter(([, method]) => method === 'POST').map(([url]) => url)
    expect(posts).toEqual(['/api/price/jobs/in-life', '/api/price/jobs/implied-funding'])
  })

  it('rend le refus du serveur comme la route synchrone', async () => {
    server([{ status: 'failed', status_code: 422, detail: 'Script invalide.' }])
    expect(await runQueuedCalculation('/api/price', {}, fast))
      .toEqual({ ok: false, status: 'failed', data: { detail: 'Script invalide.' } })
  })

  it('rend un dépôt refusé sans suivre de calcul', async () => {
    const calls = server([], { submitted: { detail: '4 calculs déjà en cours' } })
    expect(await runQueuedCalculation('/api/price', {}, fast))
      .toEqual({ ok: false, data: { detail: '4 calculs déjà en cours' } })
    expect(calls).toHaveLength(1)
  })

  it('rend le délai dépassé et l’annulation avec le message du serveur', async () => {
    server([{ status: 'timeout', detail: 'Calcul interrompu après 600 s.' }])
    expect((await runQueuedCalculation('/api/price', {}, fast)).data.detail).toBe('Calcul interrompu après 600 s.')
    server([{ status: 'cancelled', detail: 'Calcul annulé.' }])
    expect((await runQueuedCalculation('/api/price', {}, fast)).status).toBe('cancelled')
  })

  it('arrête un calcul remplacé à l’écran', async () => {
    const calls = server([{ status: 'running' }])
    const out = await runQueuedCalculation('/api/price', {}, { ...fast, isCurrent: () => false })
    expect(out.superseded).toBe(true)
    await Promise.resolve()
    expect(calls.some(([url, method]) => url === '/api/price/jobs/j1' && method === 'DELETE')).toBe(true)
  })

  it('l’annulation demande au serveur d’arrêter le calcul', async () => {
    const calls = server([])
    await cancelQueuedCalculation('j7')
    expect(calls).toEqual([['/api/price/jobs/j7', 'DELETE', undefined]])
  })

  it('refuse une route sans file plutôt que de la contourner', async () => {
    await expect(runQueuedCalculation('/api/parse', {}, fast)).rejects.toThrow('sans file')
  })
})
