import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { JOB_LABELS, JOB_ROUTES, jobChannel } from '../utils/pricingJobs.js'

// P1-4, second step: the Pricer's analyses go through the interactive queue.
// The server's jobs are driven by hand, as in pricingJobState.test.js.
const queue = vi.hoisted(() => ({ calls: [] }))
vi.mock('../utils/pricingJobs.js', async importOriginal => ({
  ...(await importOriginal()),
  runQueuedCalculation: (route, body, options) => new Promise(resolve => {
    const id = `j${queue.calls.length + 1}`
    queue.calls.push({ route, body, options, id, resolve })
    options.onState({ job_id: id, status: 'running', queue_position: null, elapsed_ms: 0 })
  }),
  cancelQueuedCalculation: async () => {},
}))
const { usePricingStore } = await import('./pricing.js')

afterEach(() => { queue.calls.length = 0; vi.unstubAllGlobals() })

function pricer() {
  setActivePinia(createPinia())
  const store = usePricingStore()
  store.script = 'AT MATURITY:\n  PAY 1'
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => (
    { ok: true, params: [], constats: [], has_maturity_event: true }) })))
  return store
}
const started = route => vi.waitFor(() => {
  const call = queue.calls.find(c => c.route === route && !c.taken)
  if (!call) throw new Error(`${route} pas encore en file`)
  call.taken = true
  return call
})

describe('analyses du Pricer dans la file de calcul', () => {
  it('chaque analyse a sa route de file et son nom à l’écran', () => {
    for (const route of ['/api/profile', '/api/paths', '/api/proba', '/api/backtest', '/api/backtest/compare',
      '/api/mtf', '/api/mtf/drilldown', '/api/solve', '/api/grid']) {
      expect(JOB_ROUTES[route]).toBeTruthy()
      expect(JOB_LABELS[route]).toBeTruthy()
    }
    // Their own process pool keeps these two out of the queue.
    expect(JOB_ROUTES['/api/scenarios']).toBeUndefined()
    expect(JOB_ROUTES['/api/mtf/compare']).toBeUndefined()
  })

  it('le prix et ses variantes forment une famille, chaque analyse la sienne', () => {
    expect(jobChannel('/api/price')).toBe(jobChannel('/api/price/in-life'))
    expect(jobChannel('/api/proba')).not.toBe(jobChannel('/api/price'))
    expect(jobChannel('/api/proba')).not.toBe(jobChannel('/api/profile'))
  })

  it('le profil passe par la file et la ligne d’état dit lequel tourne', async () => {
    const store = pricer()
    const running = store.runProfile()
    const job = await started('/api/profile')
    expect(store.pricingJob).toMatchObject({ id: job.id, route: '/api/profile', status: 'running' })
    job.resolve({ ok: true, data: { spots: [1], payoffs: [1] } })
    await running
    expect(store.profile).toEqual({ spots: [1], payoffs: [1] })
    expect(store.rightTab).toBe('profile')
    expect(store.pricingJob).toBeNull()
  })

  it('une analyse lancée pendant un prix ne remplace pas ce prix', async () => {
    const store = pricer()
    store.runPricing()
    const price = await started('/api/price')
    store.runProba()
    const proba = await started('/api/proba')
    expect(price.options.isCurrent(price.id)).toBe(true)
    expect(proba.options.isCurrent(proba.id)).toBe(true)
  })

  it('relancer la même analyse remplace la précédente', async () => {
    const store = pricer()
    store.runProba()
    const first = await started('/api/proba')
    store.runProba()
    const second = await started('/api/proba')
    expect(first.options.isCurrent(first.id)).toBe(false)
    expect(second.options.isCurrent(second.id)).toBe(true)
  })

  it('un refus du serveur s’affiche avec son message', async () => {
    const store = pricer()
    const running = store.runPaths()
    const job = await started('/api/paths')
    job.resolve({ ok: false, data: { detail: 'Script invalide.' } })
    await running
    expect(store.error).toBe('Script invalide.')
    expect(store.paths).toBeNull()
  })

  it('un calcul remplacé ne touche pas à l’écran', async () => {
    const store = pricer()
    const running = store.runProba()
    const job = await started('/api/proba')
    job.resolve({ ok: false, superseded: true, data: {} })
    await running
    expect(store.proba).toBeNull()
    expect(store.error).toBeNull()
  })
})
