// Catalogue de sous-jacents — désormais chargé depuis la base, plus codé ici.
//
// Cette liste était un tableau en dur : ajouter un titre demandait un
// développeur et un rebuild. Elle vient maintenant de la table `underlyings`,
// administrable depuis /admin/underlyings.
//
// L'export garde son nom et sa forme — un tableau [{ group, items: [{ ticker,
// label, ccy }] }] — et il est REMPLI SUR PLACE plutôt que remplacé, pour que
// les vues qui l'utilisent (`v-for`, `.flatMap`) n'aient rien à changer.

import { reactive } from 'vue'
import { apiFetch } from '../utils/api.js'

export const underlyingGroups = reactive([])

let chargement = null

/** Charge le catalogue une fois pour toutes. Idempotent : les vues peuvent
 *  l'appeler chacune à leur montage sans multiplier les requêtes. */
export function ensureUnderlyings() {
  if (underlyingGroups.length) return Promise.resolve(underlyingGroups)
  if (chargement) return chargement
  chargement = apiFetch('/api/finance/underlyings')
    .then(res => (res.ok ? res.json() : []))
    .then(groupes => {
      // Remplissage sur place : remplacer la référence casserait toutes les
      // vues qui ont importé le tableau.
      underlyingGroups.splice(0, underlyingGroups.length, ...groupes)
      return underlyingGroups
    })
    .catch(() => underlyingGroups)
    .finally(() => { chargement = null })
  return chargement
}

/** Libellé d'un ticker, ou le ticker lui-même s'il n'est pas au catalogue —
 *  un sous-jacent saisi à la main reste parfaitement valable. */
export function underlyingLabel(ticker) {
  for (const groupe of underlyingGroups) {
    const trouve = groupe.items.find(it => it.ticker === ticker)
    if (trouve) return trouve.label
  }
  return ticker
}
