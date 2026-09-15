import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../utils/api.js'
import { normaliseCorrelation } from '../utils/rfqBasket.js'

async function _json(res, fallbackMsg) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    const detail = err.detail
    if (detail && typeof detail === 'object') {
      const failures = (detail.failures || [])
        .map(f => `${f.code || 'CONTRÔLE'} — ${f.message || JSON.stringify(f)}`)
      throw new Error([detail.message || detail.code || fallbackMsg, ...failures].join('\n'))
    }
    throw new Error(detail || fallbackMsg)
  }
  return res.status === 204 ? null : res.json()
}

export const useRfqStore = defineStore('rfq', () => {
  const list      = ref([])
  const current   = ref(null)
  const providers = ref([])
  const history   = ref([])
  // Dernière réponse complète de /api/price pour l'AO courant. Le prix
  // modèle stocké côté serveur n'est qu'un nombre : sans ça, impossible de
  // montrer d'où il vient (flux par date, IC 95 %, fugit).
  const lastPricing = ref(null)
  // UI fields can emit several PATCHes in immediate succession (price, then
  // status).  The server returns the whole quote, so concurrent responses can
  // otherwise overwrite a newer price with the older snapshot.  Serialize by
  // quote while leaving different providers independent.
  const quoteUpdateQueues = new Map()

  async function fetchProviders() {
    const res = await apiFetch('/api/rfq/providers')
    providers.value = await _json(res, 'Erreur chargement fournisseurs')
  }

  async function fetchHistory() {
    const res = await apiFetch('/api/rfq/history')
    history.value = await _json(res, 'Erreur chargement historique')
  }

  async function fetchList() {
    const res = await apiFetch('/api/rfq')
    list.value = await _json(res, 'Erreur chargement RFQ')
  }

  async function fetchOne(id) {
    const res = await apiFetch(`/api/rfq/${id}`)
    // La décomposition appartient à l'AO pour lequel elle a été calculée :
    // on la jette en changeant d'AO, pas en rafraîchissant le même (ajouter
    // une cotation ne périme pas le prix modèle).
    if (lastPricing.value && lastPricing.value.rfqId !== id) lastPricing.value = null
    current.value = await _json(res, 'RFQ introuvable')
    return current.value
  }

  async function create(payload) {
    const res = await apiFetch('/api/rfq', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const rfq = await _json(res, 'Erreur création RFQ')
    list.value.unshift(rfq)
    return rfq
  }

  async function update(id, payload) {
    const res = await apiFetch(`/api/rfq/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const rfq = await _json(res, 'Erreur mise à jour RFQ')
    if (current.value?.id === id) current.value = rfq
    // Le serveur remet model_price à null dès qu'une hypothèse de pricing
    // change (api/rfq.py) : la décomposition gardée en mémoire décrirait
    // alors un prix qui n'existe plus.
    if (rfq.model_price == null && lastPricing.value?.rfqId === id) lastPricing.value = null
    const idx = list.value.findIndex(r => r.id === id)
    if (idx !== -1) list.value[idx] = rfq
    return rfq
  }

  async function remove(id) {
    const res = await apiFetch(`/api/rfq/${id}`, { method: 'DELETE' })
    await _json(res, 'Erreur suppression RFQ')
    list.value = list.value.filter(r => r.id !== id)
    if (current.value?.id === id) current.value = null
  }

  async function addQuote(rfqId, payload) {
    const res = await apiFetch(`/api/rfq/${rfqId}/quotes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const quote = await _json(res, 'Erreur ajout fournisseur')
    if (current.value?.id === rfqId) current.value.quotes.push(quote)
    return quote
  }

  async function updateQuote(rfqId, quoteId, payload) {
    const key = `${rfqId}:${quoteId}`
    const previous = quoteUpdateQueues.get(key) || Promise.resolve()
    const request = previous.catch(() => {}).then(async () => {
      const res = await apiFetch(`/api/rfq/${rfqId}/quotes/${quoteId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const quote = await _json(res, 'Erreur mise à jour quote')
      if (current.value?.id === rfqId) {
        const idx = current.value.quotes.findIndex(q => q.id === quoteId)
        if (idx !== -1) current.value.quotes[idx] = quote
      }
      return quote
    })
    quoteUpdateQueues.set(key, request)
    try {
      return await request
    } finally {
      if (quoteUpdateQueues.get(key) === request) quoteUpdateQueues.delete(key)
    }
  }

  async function removeQuote(rfqId, quoteId) {
    const res = await apiFetch(`/api/rfq/${rfqId}/quotes/${quoteId}`, { method: 'DELETE' })
    await _json(res, 'Erreur suppression quote')
    // Refetch rather than splice locally: deleting a quote can cascade to
    // its last-look child and/or clear the RFQ's selected_quote_id
    // server-side (see api/rfq.py delete_quote) — a local filter would miss
    // both.
    if (current.value?.id === rfqId) await fetchOne(rfqId)
  }

  // Toggling last_look changes the shape of the quotes list (adds/removes a
  // linked child row) rather than just one field on one row, so refetch the
  // whole RFQ instead of trying to patch the array in place.
  async function toggleLastLook(rfqId, quoteId, value) {
    await updateQuote(rfqId, quoteId, { last_look: value })
    if (current.value?.id === rfqId) await fetchOne(rfqId)
  }

  function selectQuote(rfqId, quoteId) {
    return update(rfqId, { selected_quote_id: quoteId })
  }

  function addDaysIso(isoDate, days) {
    const date = new Date(`${isoDate}T00:00:00Z`)
    date.setUTCDate(date.getUTCDate() + Math.round(days))
    return date.toISOString().slice(0, 10)
  }

  function rfqMaturityDate(p) {
    if (p.maturity_date) return p.maturity_date
    const dates = []
    for (const value of Object.values(p.constats || {})) {
      if (typeof value === 'string') dates.push(value)
      else if (value?.end_date) dates.push(value.end_date)
    }
    if (dates.length) return dates.sort().at(-1)
    const origin = p.strike_date || p.value_date
    return origin && p.T ? addDaysIso(origin, p.T * 365.25) : null
  }

  // Prices the RFQ's frozen script against the same dated route as the Pricer.
  // A historical or forward-start tender must replay/simulate its initial
  // fixing relative to the valuation date; /api/price only represents t=0.
  async function computeModelPrice(rfq) {
    const p = rfq.params || {}
    const valuationDate = p.valuation_date || rfq.ao_date || new Date().toISOString().slice(0, 10)
    const dated = !!(p.strike_date && valuationDate !== p.strike_date)
    const maturityDate = rfqMaturityDate(p)
    if (dated && !maturityDate) {
      throw new Error('La maturité contractuelle est requise pour valoriser cette RFQ à sa date.')
    }
    const payload = {
      script: rfq.script_snapshot,
      underlyings: p.underlyings || [],
      corr_matrix: normaliseCorrelation(p.corr_matrix, (p.underlyings || []).length),
      r: p.r ?? 0.03,
      T: p.T ?? 3.0,
      N: p.N ?? 20000,
      model: p.model || 'constant',
      antithetic: p.antithetic ?? true,
      yield_curve: p.yield_curve || [],
      funding_curve: p.funding_curve || [],
      funding_spread: p.funding_spread ?? 0,
      sigma_r: p.sigma_r ?? 0,
      a_r: p.a_r ?? 0,
      barrier_monitoring: p.barrier_monitoring || 'weekly',
      user_params: p.user_params || {},
      constats: p.constats || {},
      frozen_schedule: p.frozen_schedule || null,
      strike_date: p.strike_date || null,
      value_date: p.value_date || null,
      payment_date: p.payment_date || null,
      maturity_date: maturityDate,
      settlement_ccy: p.currency || null,
      anchor: p.strike_date || p.value_date || null,
      ...(dated ? { valuation_date: valuationDate } : {}),
    }
    const res = await apiFetch(dated ? '/api/price/in-life' : '/api/price', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await _json(res, 'Erreur calcul du prix modèle')
    if (data.early_recall || data.price == null) {
      const recallDate = data.recall_date ? ` le ${data.recall_date}` : ''
      throw new Error(data.message || `Le produit a déjà été rappelé${recallDate} : aucun prix actif à comparer.`)
    }
    // On garde la réponse entière, pas seulement le prix : c'est elle qui
    // permet au détail de l'AO d'expliquer le chiffre qu'on oppose au
    // fournisseur, ligne de flux par ligne de flux.
    lastPricing.value = {
      rfqId: rfq.id,
      result: data,
      // Le strike ancre l'axe des temps du moteur : c'est lui qui reconvertit
      // un t en date. La value date ne reste que comme repli.
      strikeDate: p.strike_date || null,
      valueDate: p.value_date || null,
      hypotheses: {
        model: p.model || 'constant',
        r: p.r ?? null,
        N: p.N ?? null,
        underlyings: (p.underlyings || []).map(underlying => ({
          name: underlying.name, ticker: underlying.ticker,
          sigma: underlying.sigma ?? null, q: underlying.q ?? null,
        })),
        corr_matrix: normaliseCorrelation(p.corr_matrix, (p.underlyings || []).length),
      },
      at: new Date().toISOString(),
    }
    // /api/price returns a 0–1 fraction of nominal; quotes are entered in
    // percentage points (e.g. 98.5), so scale to match before comparing.
    return update(rfq.id, { model_price: data.price * 100 })
  }

  return {
    list, current, providers, history, lastPricing,
    fetchProviders, fetchList, fetchOne, create, update, remove,
    addQuote, updateQuote, removeQuote, computeModelPrice, fetchHistory,
    toggleLastLook, selectQuote,
  }
})
