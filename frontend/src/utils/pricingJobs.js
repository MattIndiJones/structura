// File de calcul interactive du serveur (P1-4) : le prix, les Greeks et le
// spread implicite tournent dans un processus de calcul que l'écran suit et
// peut arrêter. Le serveur l'arrête aussi au-delà de son délai, ou quand plus
// aucun écran ne le suit.
import { apiFetch } from './api.js'

export const JOB_ROUTES = {
  '/api/price': 'price',
  '/api/price/in-life': 'in-life',
  '/api/price/implied-funding': 'implied-funding',
}
export const JOB_TERMINAL = new Set(['done', 'failed', 'cancelled', 'timeout', 'abandoned'])

const pause = ms => new Promise(resolve => setTimeout(resolve, ms))

/**
 * Lance le calcul de `route` dans la file et le suit jusqu'au bout.
 *
 * Rend `{ ok, data }` comme la route synchrone : `data` est le résultat, ou
 * le corps d'erreur (`detail`). `superseded` vaut true si `isCurrent` a dit
 * qu'un autre calcul avait pris sa place : celui-ci est alors arrêté.
 * `onState` reçoit chaque état lu (`job_id`, `status`, `queue_position`,
 * `elapsed_ms`).
 */
export async function runQueuedCalculation(route, body, {
  onState = () => {}, isCurrent = () => true, firstDelay = 120, maxDelay = 600,
} = {}) {
  const kind = JOB_ROUTES[route]
  if (!kind) throw new Error(`Calcul sans file : ${route}`)
  const submitted = await apiFetch(`/api/price/jobs/${kind}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const first = await submitted.json()
  if (!submitted.ok) return { ok: false, data: first }
  const id = first.job_id
  onState(first)
  for (let delay = firstDelay; ; delay = Math.min(delay * 1.5, maxDelay)) {
    await pause(delay)
    if (!isCurrent(id)) {
      cancelQueuedCalculation(id).catch(() => {})
      return { ok: false, superseded: true, data: {} }
    }
    const res = await apiFetch(`/api/price/jobs/${id}`)
    const state = await res.json()
    if (!res.ok) return { ok: false, data: state }
    onState(state)
    if (state.status === 'done') return { ok: true, data: state.result }
    if (JOB_TERMINAL.has(state.status)) return { ok: false, status: state.status, data: { detail: state.detail } }
  }
}

/** Demande l'arrêt d'un calcul : le serveur tue son processus. */
export function cancelQueuedCalculation(id) {
  return apiFetch(`/api/price/jobs/${id}`, { method: 'DELETE' })
}
