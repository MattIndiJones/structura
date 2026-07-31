import { reactive, computed, ref, unref } from 'vue'

// Filtrage + tri d'une liste d'enregistrements, généralisés depuis le
// mécanisme de l'onglet Deals du Booking (le seul de l'app à l'avoir, et
// celui que Philippe voulait partout) : quelques champs, dont les options
// sortent des données elles-mêmes plutôt que d'une liste figée, un tri avec
// son sens, un compteur « affichés / total » et une remise à zéro qui ne
// s'affiche que s'il y a quelque chose à remettre à zéro.
//
// Un champ se décrit ainsi :
//   { key, label, kind: 'text' | 'select', get?, options?, width? }
//     get      — accesseur (défaut : row => row[key]) ; indispensable dès que
//                la valeur est imbriquée (le ticker d'un sous-jacent) ou
//                dérivée (le libellé d'un statut).
//     options  — pour un 'select' : liste figée, ou omise pour laisser les
//                valeurs présentes dans les données la construire.
//     match    — comparaison sur mesure (défaut : égalité stricte pour un
//                select, sous-chaîne insensible à la casse pour un texte).
//                Le cas « une ligne a plusieurs valeurs » (un panier de
//                sous-jacents) passe par là.
//
// Un tri se décrit ainsi : { key, label, get? }.

function _defaultGet(key) {
  return row => row?.[key]
}

function _norm(v) {
  return String(v ?? '').toLowerCase()
}

function compareValues(a, b) {
  // Les vides toujours en dernier, quel que soit le sens : une valeur non
  // renseignée n'a pas de rang, la placer en tête d'un tri décroissant serait
  // arbitraire.
  const aEmpty = a === null || a === undefined || a === ''
  const bEmpty = b === null || b === undefined || b === ''
  if (aEmpty || bEmpty) return aEmpty && bEmpty ? 0 : (aEmpty ? 1 : -1)
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return (a ? 1 : 0) - (b ? 1 : 0)
  return String(a).localeCompare(String(b), 'fr', { numeric: true, sensitivity: 'base' })
}

export function useDataFilter(rows, fields, options = {}) {
  // `fields` accepte un tableau figé ou un computed : l'écran Données de
  // l'admin sert sept tables aux colonnes différentes et déduit ses filtres
  // de celle qui est affichée. L'état n'est donc pas pré-semé — une clé
  // absente vaut « pas de filtre », ce qui évite de recréer le composable (et
  // de perdre la saisie en cours) à chaque changement de colonnes.
  const _fields = computed(() => unref(fields))
  const state = reactive({})

  const sortBy = ref(options.defaultSort || '')
  const sortDir = ref(options.defaultSortDir || 'asc')

  // Options de chaque select : les valeurs réellement présentes dans les
  // données, dédoublonnées et triées. Proposer un filtre qui ne ramène rien
  // est une impasse — autant ne pas l'offrir.
  const fieldOptions = computed(() => {
    const out = {}
    for (const f of _fields.value) {
      if (f.kind !== 'select') continue
      if (f.options) { out[f.key] = f.options; continue }
      const get = f.get || _defaultGet(f.key)
      const seen = new Set()
      for (const row of rows.value || []) {
        const v = get(row)
        for (const one of Array.isArray(v) ? v : [v]) {
          if (one !== null && one !== undefined && one !== '') seen.add(one)
        }
      }
      out[f.key] = [...seen].sort((a, b) => compareValues(a, b))
    }
    return out
  })

  const hasActiveFilters = computed(() => _fields.value.some(f => state[f.key]))

  function reset() {
    for (const k of Object.keys(state)) delete state[k]
  }

  function toggleSortDir() {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  }

  const filtered = computed(() => {
    let list = (rows.value || []).filter(row => _fields.value.every(f => {
      const needle = state[f.key]
      if (needle === '' || needle === null || needle === undefined) return true
      const get = f.get || _defaultGet(f.key)
      const value = get(row)
      if (f.match) return f.match(row, needle)
      if (f.kind === 'text') {
        const hay = Array.isArray(value) ? value.map(_norm).join(' ') : _norm(value)
        return hay.includes(_norm(needle))
      }
      return Array.isArray(value) ? value.some(v => String(v) === String(needle))
                                  : String(value ?? '') === String(needle)
    }))

    const sort = (options.sorts || []).find(s => s.key === sortBy.value)
    if (sort) {
      const get = sort.get || _defaultGet(sort.key)
      const dir = sortDir.value === 'asc' ? 1 : -1
      // Copie : trier en place réordonnerait la source et ferait perdre
      // l'ordre d'origine, qu'on peut vouloir retrouver.
      list = [...list].sort((a, b) => {
        const av = get(a); const bv = get(b)
        const aEmpty = av === null || av === undefined || av === ''
        const bEmpty = bv === null || bv === undefined || bv === ''
        if (aEmpty || bEmpty) return aEmpty && bEmpty ? 0 : (aEmpty ? 1 : -1)
        return dir * compareValues(av, bv)
      })
    }
    return list
  })

  return { state, fieldOptions, hasActiveFilters, reset, sortBy, sortDir, toggleSortDir, filtered }
}
