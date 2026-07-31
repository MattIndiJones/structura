import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../utils/api.js'

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

  // Prices the RFQ's frozen script against Structura's own Monte Carlo engine
  // (same /api/price endpoint the Pricer uses) and stores the result on the RFQ.
  async function computeModelPrice(rfq) {
    const p = rfq.params || {}
    const res = await fetch('/api/price', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        script: rfq.script_snapshot,
        underlyings: p.underlyings || [],
        corr_matrix: p.corr_matrix || [],
        r: p.r ?? 0.03,
        T: p.T ?? 3.0,
        N: p.N ?? 20000,
        model: p.model || 'constant',
        user_params: p.user_params || {},
        constats: p.constats || {},
        // Value date = the product's t=0, what the CONSTAT calendar's dates
        // are counted from (see PricingRequest.anchor). Without it the RFQ
        // prices its calendar from today and the deal booked out of it
        // reprices from its value date — same product, two prices.
        anchor: p.value_date || null,
      }),
    })
    const data = await _json(res, 'Erreur calcul du prix modèle')
    // /api/price returns a 0–1 fraction of nominal; quotes are entered in
    // percentage points (e.g. 98.5), so scale to match before comparing.
    return update(rfq.id, { model_price: data.price * 100 })
  }

  return {
    list, current, providers, history,
    fetchProviders, fetchList, fetchOne, create, update, remove,
    addQuote, updateQuote, removeQuote, computeModelPrice, fetchHistory,
    toggleLastLook, selectQuote,
  }
})
