import { computed, ref } from 'vue'
import { sortValuationRuns } from '../utils/valuationComparison'

export function useValuationRunSelection(runs) {
  const ids = ref([]), inverted = ref(false)
  const selected = computed(() => {
    const ordered = sortValuationRuns(runs.value.filter(r => ids.value.includes(r.id)))
    return inverted.value ? ordered.reverse() : ordered
  })
  function reset(values = [], preserveOrder = false) {
    ids.value = [...new Set(values.map(Number))].filter(id => runs.value.some(r => r.id === id)).slice(0, 2)
    inverted.value = false
    if (preserveOrder && ids.value.length === 2 && selected.value[0].id !== ids.value[0]) inverted.value = true
  }
  function toggle(id) {
    if (ids.value.includes(id)) ids.value = ids.value.filter(v => v !== id)
    else if (ids.value.length < 2 && runs.value.some(r => r.id === id)) ids.value = [...ids.value, id]
    else return
    inverted.value = false
  }
  return { ids, selected, reset, toggle, invert: () => { if (ids.value.length === 2) inverted.value = !inverted.value } }
}

export function runSelectionWarnings(runs) {
  if (runs.length !== 2) return []
  const [a, b] = runs
  const market = r => (typeof r.result?.mtm === 'object' ? r.result.mtm : r.result)?.market_used || {}
  const ma = market(a), mb = market(b), warnings = []
  if (ma.source !== mb.source) warnings.push('Les bases de marché diffèrent : paramètres du booking et/ou marché actualisé.')
  if (ma.model !== mb.model) warnings.push('Les modèles diffèrent : seul l’écart observé pourra être présenté, sans attribution causale.')
  for (const [key, label] of [['contract_version', 'Versions contractuelles différentes'], ['engine_fingerprint', 'Versions du moteur différentes'], ['n_paths', 'Nombres de trajectoires différents']]) {
    if (a[key] != null && b[key] != null && a[key] !== b[key]) warnings.push(`${label} : l’attribution peut être indisponible.`)
  }
  const keys = ['r', 'sigma', 'q', 'corr', 'window_returns']
  if (keys.some(k => JSON.stringify(ma[k]) !== JSON.stringify(mb[k]))) warnings.push('Les paramètres de marché enregistrés diffèrent. L’explication s’appuiera sur les valeurs propres à chaque calcul.')
  return warnings
}
