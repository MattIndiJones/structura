/**
 * Aperçu des constatations d'un produit : leurs dates, et les clôtures
 * réellement relevées à celles qui sont passées.
 *
 * Trois écrans montraient ce tableau — l'onglet Deal, l'onglet Events et le
 * panneau de résultats — chacun avec sa propre arithmétique de dates, et
 * chacun avec ses propres erreurs. Events allait jusqu'à deviner la date de
 * strike comme « date de valeur moins deux jours ». Une seule source ici,
 * pour que les trois disent la même chose.
 *
 * Deux pièges que ce module existe pour éviter :
 *
 *  1. L'axe des temps du moteur part de la DATE DE STRIKE, pas de la value
 *     date : c'est là que le niveau initial se constate et que la diffusion
 *     démarre. L'ancrer ailleurs décale toutes les échéances de l'écart entre
 *     les deux dates.
 *
 *  2. En cours de vie, seule la vie restante est simulée : les temps de la
 *     table de flux se comptent alors depuis la DATE DE VALORISATION. Les
 *     ancrer sur le strike ramène les constatations futures des années en
 *     arrière, toutes marquées passées. Le passé, lui, est dans
 *     `past.realized_flows`, compté depuis le strike.
 */
import { computed, ref, watch } from 'vue'

export function addDaysStr(isoDate, days) {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + Math.round(days))
  return d.toISOString().split('T')[0]
}

export function todayStr() {
  return new Date().toISOString().split('T')[0]
}

/**
 * @param {object} store        store de pricing (result, scriptConstats,
 *                              constatOverrides, underlyings, globalParams)
 * @param {function} strikeDate () => 'YYYY-MM-DD' — origine de l'axe
 * @param {function} devise     () => 'EUR' — calendrier de règlement
 */
export function useObservationPreview(store, strikeDate, devise) {
  // Dates exactes du calendrier CONSTAT quand il y en a un. Elles priment sur
  // tout : ce sont les dates contractuelles, pas des pas de grille.
  const datesCalendrier = ref([])
  const closesPassees = ref({})   // { 'YYYY-MM-DD': { ticker: cours } }

  function _tenor(t) { return (t && t.value) ? `${t.value}${t.unit}` : null }

  async function chargerCalendrier() {
    const calendriers = (store.scriptConstats || []).filter(c => c.kind !== 'single')
    if (!calendriers.length) { datesCalendrier.value = []; return }
    const toutes = new Set()
    for (const c of calendriers) {
      const v = store.constatOverrides[c.name] || {}
      if (!v.start_date || !v.end_date) continue
      try {
        const res = await fetch('/api/schedule/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            start_date: v.start_date, end_date: v.end_date, roll_date: v.roll_date,
            frequency: _tenor(v.frequency), stub: v.stub,
            sub_frequency: _tenor(v.sub_frequency) || null,
            currency: devise() || 'EUR',
            convention: v.convention || 'none',
            settlement_lag: v.settlement_lag || 0,
          }),
        })
        if (!res.ok) continue
        const data = await res.json()
        // La première date est le début de période, pas une observation.
        ;(data.dates || []).slice(1).forEach(d => toutes.add(d))
      } catch { /* calendrier incomplet : on retombe sur les flux */ }
    }
    datesCalendrier.value = [...toutes].sort()
  }

  /** Les temps de constatation lus dans la table de flux du dernier pricing. */
  const tempsDeFlux = computed(() => {
    const ft = store.result?.flux_table
    if (!ft) return []
    return [...new Set(Object.values(ft).map(e => e.t))].sort((a, b) => a - b)
  })

  /** Dates de constatation, calendrier contractuel en priorité. */
  const datesObservations = computed(() => {
    if (datesCalendrier.value.length) return datesCalendrier.value
    const origine = strikeDate()
    if (!origine) return []
    const res = store.result
    if (res?.in_life && res.valuation_date) {
      const passees = [...new Set((res.past?.realized_flows || []).map(f => f.t))]
        .sort((a, b) => a - b)
        .map(t => addDaysStr(origine, t * 365.25))
      const futures = tempsDeFlux.value.map(t => addDaysStr(res.valuation_date, t * 365.25))
      return [...passees, ...futures]
    }
    return tempsDeFlux.value.map(t => addDaysStr(origine, t * 365.25))
  })

  async function chargerCloturesPassees() {
    const aujourdhui = todayStr()
    const jours = new Set(datesObservations.value)
    const origine = strikeDate()
    if (origine) jours.add(origine)   // le strike est la constatation la plus utile
    const passees = [...jours].filter(d => d <= aujourdhui).sort()
    const tickers = (store.underlyings || []).map(u => u.ticker).filter(Boolean)
    if (!passees.length || !tickers.length) { closesPassees.value = {}; return }
    try {
      const debut = addDaysStr(passees[0], -10)
      const q = new URLSearchParams({ tickers: tickers.join(','), start: debut, end: aujourdhui })
      const res = await fetch(`/api/finance/hist_prices?${q}`)
      if (!res.ok) return
      const data = await res.json()
      const dates = data.dates || []
      const releve = {}
      for (const jour of passees) {
        // Dernière clôture connue à cette date : un jour fermé n'a pas de
        // cours, c'est celui d'avant qui fait foi — la convention du replay.
        let idx = -1
        for (let i = 0; i < dates.length; i++) { if (dates[i] <= jour) idx = i; else break }
        if (idx < 0) continue
        releve[jour] = {}
        for (const tk of tickers) {
          const serie = data.prices?.[tk]
          if (serie && serie[idx]) releve[jour][tk] = serie[idx]
        }
      }
      closesPassees.value = releve
    } catch { /* pas d'historique : les cellules restent vides */ }
  }

  /**
   * Les relevés de chaque constatation moyennée, indexés par date de
   * constatation. Ils viennent de l'échéancier que le backend résout — la
   * MÊME structure que celle figée au booking — plutôt que d'une arithmétique
   * de dates refaite ici : c'est tout l'intérêt d'avoir une source unique.
   */
  const relevesParConstatation = computed(() => {
    const par = {}
    for (const c of store.result?.schedule?.constatations || []) {
      if (c.reduction && c.releves?.length && c.date) par[c.date] = c
    }
    return par
  })

  /** Lignes prêtes à afficher : strike, constatations, leurs relevés, maturité. */
  const previewEvents = computed(() => {
    const origine = strikeDate()
    if (!origine) return []
    if (!store.result && !datesCalendrier.value.length) return []
    const aujourdhui = todayStr()
    const lignes = datesObservations.value.map(date => ({
      date,
      t: Math.round(((new Date(date) - new Date(origine)) / 86400000 / 365.25) * 1e4) / 1e4,
    }))
    const events = [{
      label: 'Strike / Fixing S₀', date: origine, t: 0, isFuture: origine > aujourdhui,
    }]
    lignes.forEach(({ date, t }, idx) => {
      const label = idx === lignes.length - 1 ? 'Maturité' : `Obs. ${idx + 1}`
      const constatee = relevesParConstatation.value[date]
      events.push({
        label, date, t, isFuture: date > aujourdhui,
        reduction: constatee?.reduction || null,
        nbReleves: constatee?.releves?.length || 0,
      })
      // Une constatation moyennée n'est pas observable directement : elle se
      // calcule depuis ces cours-là. Les montrer, c'est montrer le produit —
      // et ce sont eux dont il faudra relever le fixing en vie.
      for (const [j, r] of (constatee?.releves || []).entries()) {
        if (r.date === date) continue     // le dernier relevé EST la constatation
        events.push({
          label: `relevé ${j + 1}/${constatee.releves.length}`,
          date: r.date, t: r.t, isFuture: r.date > aujourdhui,
          estReleve: true, evenement: !!r.evenement,
        })
      }
    })
    return events
  })

  watch(() => [store.scriptConstats, store.constatOverrides, strikeDate()],
        chargerCalendrier, { deep: true, immediate: true })
  watch(datesObservations, chargerCloturesPassees, { immediate: true })

  return { datesCalendrier, datesObservations, closesPassees, previewEvents }
}
