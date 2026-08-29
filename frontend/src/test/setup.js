/**
 * Le minimum de navigateur dont le store a besoin.
 *
 * `utils/api.js` lit le jeton d'authentification dans `localStorage` — c'est le
 * seul emprunt au navigateur sur le chemin qu'on teste. Un faux suffit ; tirer
 * jsdom pour une méthode rendrait chaque exécution plus lente sans rien couvrir
 * de plus.
 */
const stockage = new Map()

globalThis.localStorage = {
  getItem: (k) => (stockage.has(k) ? stockage.get(k) : null),
  setItem: (k, v) => stockage.set(k, String(v)),
  removeItem: (k) => stockage.delete(k),
  clear: () => stockage.clear(),
}
