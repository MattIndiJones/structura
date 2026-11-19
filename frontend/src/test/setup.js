/**
 * Le minimum de navigateur dont le store a besoin.
 *
 * `utils/api.js` lit le jeton d'authentification dans `localStorage` — c'est le
 * seul emprunt au navigateur sur le chemin qu'on teste. Un faux suffit ; tirer
 * jsdom pour une méthode rendrait chaque exécution plus lente sans rien couvrir
 * de plus.
 */
import { beforeEach, vi } from 'vitest'
const stockage = new Map(), sessions = new Map()

globalThis.localStorage = {
  getItem: (k) => (stockage.has(k) ? stockage.get(k) : null),
  setItem: (k, v) => stockage.set(k, String(v)),
  removeItem: (k) => stockage.delete(k),
  clear: () => stockage.clear(),
}
globalThis.sessionStorage = {
  getItem: (k) => sessions.has(k) ? sessions.get(k) : null,
  setItem: (k, v) => sessions.set(k, String(v)),
  removeItem: (k) => sessions.delete(k),
  clear: () => sessions.clear(),
}
beforeEach(() => sessionStorage.clear())

/**
 * La file de calcul interactive (P1-4) ramenée à la route synchrone.
 *
 * Les tests du store décrivent ce que l'écran envoie à `/api/price` et ce
 * qu'il fait de la réponse : ils simulent `fetch` sur ces routes. Le protocole
 * de la file — dépôt, suivi, annulation — se teste à part, dans
 * `utils/pricingJobs.test.js`, contre le vrai module.
 */
vi.mock('../utils/pricingJobs.js', async importOriginal => {
  const actual = await importOriginal()
  const { apiFetch } = await import('../utils/api.js')
  return {
    ...actual,
    runQueuedCalculation: async (route, body) => {
      const res = await apiFetch(route, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      return { ok: res.ok, data: await res.json() }
    },
    cancelQueuedCalculation: async () => {},
  }
})
