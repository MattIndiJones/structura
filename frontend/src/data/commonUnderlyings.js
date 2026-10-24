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
import { sessionToken, sessionInstallation } from '../utils/session.js'

export const underlyingGroups = reactive([])

let chargement = null
let context = null, generation = 0, loadedAt = 0
export const CATALOG_CACHE_MS = 30000
export function clearUnderlyings() {
  generation++
  chargement = null; context = null; loadedAt = 0
  underlyingGroups.splice(0)
}

/** Charge le catalogue une fois pour toutes. Idempotent : les vues peuvent
 *  l'appeler chacune à leur montage sans multiplier les requêtes. */
export function ensureUnderlyings({ force = false } = {}) {
  const activeContext = JSON.stringify([sessionToken(), sessionInstallation()?.installation_id || null])
  if (context !== activeContext) { clearUnderlyings(); context = activeContext }
  if (!force && loadedAt && Date.now() - loadedAt < CATALOG_CACHE_MS) return Promise.resolve(underlyingGroups)
  if (!force && chargement) return chargement
  const version = ++generation
  const request = apiFetch('/api/finance/underlyings')
    .then(async res => { if (!res.ok) throw new Error('Référentiel indisponible.'); return res.json() })
    .then(groupes => {
      if (version !== generation || activeContext !== JSON.stringify([sessionToken(), sessionInstallation()?.installation_id || null])) return underlyingGroups
      // Remplissage sur place : remplacer la référence casserait toutes les
      // vues qui ont importé le tableau.
      underlyingGroups.splice(0, underlyingGroups.length, ...groupes)
      loadedAt = Date.now()
      return underlyingGroups
    })
    .catch(() => {
      if (version === generation) { loadedAt = 0; underlyingGroups.splice(0) }
      return underlyingGroups
    })
    .finally(() => { if (version === generation) chargement = null })
  chargement = request
  return request
}

export function catalogInstrument(ticker) {
  return underlyingGroups.flatMap(group => group.items).find(item => item.ticker === ticker)
}

export function selectCatalogUnderlying(target, ticker, script = '') {
  const matches = underlyingGroups.flatMap(group => group.items).filter(item => item.ticker === ticker)
  if (!matches.length) { target.ticker = ticker; return false }
  if (new Set(matches.map(item => item.ccy)).size !== 1 || !matches[0].ccy) throw new Error('Devise du titre à qualifier dans le référentiel.')
  const item = matches[0]
  const aliasUsed = target.name && script.includes(target.name)
  Object.assign(target, { ticker, name: aliasUsed ? target.name : item.label, ccy: item.ccy })
  return true
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
