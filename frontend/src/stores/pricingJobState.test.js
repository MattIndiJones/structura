import { afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// The real queue protocol is tested in utils/pricingJobs.test.js. Here the
// server's job is driven by hand to see what the Pricer shows and stops.
const queue = vi.hoisted(() => ({ run: null, cancel: null }))
vi.mock('../utils/pricingJobs.js', async importOriginal => ({
  ...(await importOriginal()),
  runQueuedCalculation: (...args) => queue.run(...args),
  cancelQueuedCalculation: (...args) => queue.cancel(...args),
}))

const { usePricingStore } = await import('./pricing.js')

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

function pricer() {
  setActivePinia(createPinia())
  const store = usePricingStore()
  store.script = 'AT MATURITY:\n  PAY 1'
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => (
    { ok: true, params: [], constats: [], has_maturity_event: true }) })))
  return store
}

it('le Pricer suit le calcul de la file puis l’oublie', async () => {
  const store = pricer()
  let finish
  queue.run = vi.fn((route, body, { onState }) => new Promise(resolve => {
    onState({ job_id: 'j1', status: 'queued', queue_position: 2, elapsed_ms: 0 })
    finish = () => { onState({ job_id: 'j1', status: 'done' }); resolve({ ok: true, data: { price: .97, ic95: [.96, .98] } }) }
  }))
  const running = store.runPricing()
  await vi.waitFor(() => expect(store.pricingJob).toMatchObject({ id: 'j1', status: 'queued', queue_position: 2 }))
  expect(store.loading).toBe(true)
  expect(queue.run.mock.calls[0][0]).toBe('/api/price')
  finish()
  await running
  expect(store.pricingJob).toBeNull()
  expect(store.result.price).toBe(.97)
})

it('Annuler arrête le calcul côté serveur et rend la main avec son message', async () => {
  const store = pricer()
  let settle
  queue.run = vi.fn((route, body, { onState }) => new Promise(resolve => {
    onState({ job_id: 'j2', status: 'running', elapsed_ms: 1200 })
    settle = resolve
  }))
  queue.cancel = vi.fn(async () => {
    settle({ ok: false, status: 'cancelled', data: { detail: 'Calcul annulé.' } })
  })
  const running = store.runPricing()
  await vi.waitFor(() => expect(store.pricingJob?.status).toBe('running'))
  await store.cancelPricing()
  expect(queue.cancel).toHaveBeenCalledWith('j2')
  await running
  expect(store.error).toBe('Calcul annulé.')
  expect(store.loading).toBe(false)
  expect(store.pricingJob).toBeNull()
  expect(store.result).toBeNull()
})

it('un second clic sur Annuler ne redemande pas l’arrêt', async () => {
  const store = pricer()
  queue.run = vi.fn((route, body, { onState }) => new Promise(() => {
    onState({ job_id: 'j3', status: 'running', elapsed_ms: 0 })
  }))
  queue.cancel = vi.fn(async () => {})
  store.runPricing()
  await vi.waitFor(() => expect(store.pricingJob?.status).toBe('running'))
  await store.cancelPricing()
  await store.cancelPricing()
  expect(queue.cancel).toHaveBeenCalledTimes(1)
  expect(store.pricingJob.status).toBe('cancelling')
})
