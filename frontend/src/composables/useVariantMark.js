/**
 * Les trois états visuels d'un champ dans une variante.
 *
 * La règle qui gouverne tout ce fichier : **aucune valeur ne s'affiche sans
 * dire de quel état elle relève.** Un champ modifié qui aurait l'air neutre
 * ferait croire à une comparaison « toutes choses égales par ailleurs » qui
 * n'en est pas une, et c'est le genre d'erreur qui ne se voit pas sur un prix.
 *
 *   hérité   neutre, comme partout ailleurs dans l'écran
 *   modifié  ambre — ni bleu, déjà l'accent d'interaction, ni vert/rouge,
 *            déjà la sémantique P&L. Un « changé » coloré en rouge se lirait
 *            comme une perte.
 *   retiré   grisé barré, TOUJOURS affiché. C'est la raison d'être du modèle
 *            en delta : une copie ne saurait pas qu'un titre a existé.
 *
 * Les marques viennent du serveur (`ecarts`), jamais d'une comparaison refaite
 * ici. Recalculer un diff à l'écran le ferait diverger de celui qui a servi à
 * pricer, et l'écran mentirait avec application.
 */
import { computed } from 'vue'

/** Normalise un chemin comme le fait `canonique()` côté serveur. */
export function cheminParam(nom) { return `params[${nom}]` }
export function cheminConstat(nom, champ) { return `constats[${nom}].${champ}` }
export function cheminSousJacent(nom, champ) {
  return champ ? `underlyings[${nom}].${champ}` : `underlyings[${nom}]`
}
export function cheminGlobal(cle) { return `global.${cle}` }

export const CLASSES = {
  modifie: 'ring-1 ring-amber-500/60 bg-amber-500/5',
  retire: 'opacity-40 line-through pointer-events-none select-none',
}

export function useVariantMark(store) {
  /** chemin → {etat, avant, apres}. Vide hors variante. */
  const parChemin = computed(() => {
    const m = new Map()
    for (const e of store.variantInfo?.ecarts || []) m.set(e.chemin, e)
    return m
  })

  const estVariante = computed(() => !!store.variantInfo)
  const nbEcarts = computed(() => parChemin.value.size)

  /** 'modifie' | 'retire' | null */
  function etat(chemin) {
    return parChemin.value.get(chemin)?.etat || null
  }

  /** La valeur d'origine, pour écrire « 50 % → 30 % » ou griser un retiré. */
  function avant(chemin) {
    return parChemin.value.get(chemin)?.avant
  }

  /** Les classes à poser sur le champ. Chaîne vide si hérité. */
  function classe(chemin) {
    return CLASSES[etat(chemin)] || ''
  }

  /**
   * Les éléments RETIRÉS d'un espace, avec leur fiche d'origine.
   *
   * L'écran les rend en grisé à leur place d'origine, plutôt que de les faire
   * disparaître : « on l'a enlevé » et « il n'y a jamais été » sont deux choses
   * différentes, et c'est celle-là qu'on veut lire.
   */
  function retires(espace) {
    const prefixe = `${espace}[`
    return [...parChemin.value.values()].filter(
      e => e.etat === 'retire' && e.chemin.startsWith(prefixe) && !e.chemin.includes('].'))
  }

  return { estVariante, nbEcarts, parChemin, etat, avant, classe, retires }
}

/** Le libellé lisible d'un chemin, pour le panneau de différences. */
export function libelleChemin(chemin) {
  if (chemin === 'script') return 'Payoff (script)'
  const m = /^(params|constats|underlyings)\[([^\]]+)\](?:\.(.+))?$/.exec(chemin)
  if (m) {
    const espace = { params: 'Paramètre', constats: 'Calendrier',
                     underlyings: 'Sous-jacent' }[m[1]]
    return m[3] ? `${espace} ${m[2]} — ${CHAMPS[m[3]] || m[3]}` : `${espace} ${m[2]}`
  }
  const cle = chemin.replace(/^global\./, '')
  return CHAMPS[cle] || cle
}

const CHAMPS = {
  start_date: 'début', end_date: 'fin', roll_date: 'date de roll',
  frequency: 'fréquence', convention: 'convention', settlement_lag: 'décalage de règlement',
  stub: 'stub', strike_date: 'constatation initiale', value_date: 'date de valeur',
  payment_date: 'règlement final', valuation_date: 'date de valorisation',
  trade_date: 'date de négociation', sigma: 'volatilité', q: 'dividende',
  r: 'taux', T: 'maturité (ans)', model: 'modèle', corr_matrix: 'corrélation',
  underlyings: 'panier',
}

/** Une valeur d'écart, rendue lisible dans le panneau. */
export function valeurLisible(v) {
  if (v == null) return '—'
  if (typeof v === 'number') {
    return v.toLocaleString('fr-FR', { maximumFractionDigits: 6 })
  }
  if (typeof v === 'string') {
    // Un script entier ne se montre pas dans une ligne de diff.
    return v.length > 60 ? `${v.slice(0, 57)}…` : v
  }
  if (v && typeof v === 'object' && v.name) return v.name
  return JSON.stringify(v)
}
