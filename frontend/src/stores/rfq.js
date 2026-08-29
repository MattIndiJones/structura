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
  // Dernière réponse complète de /api/price pour l'AO courant. Le prix
  // modèle stocké côté serveur n'est qu'un nombre : sans ça, impossible de
  // montrer d'où il vient (flux par date, IC 95 %, fugit).
  const lastPricing = ref(null)

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
    const res = await apiFetch('/api/price', {
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
        // Les hypothèses de marché stockées avec l'AO. Sans ce passage, elles
        // étaient saisissables, enregistrées… et sans le moindre effet sur le
        // prix modèle. Le projet a déjà connu ce fil débranché : une courbe de
        // dividende à 8 % vaut −491,6 bps.
        yield_curve: p.yield_curve || [],
        funding_curve: p.funding_curve || [],
        funding_spread: p.funding_spread ?? 0,
        user_params: p.user_params || {},
        constats: p.constats || {},
        // Trois dates, trois rôles distincts : la diffusion démarre au
        // strike (c'est là que le niveau initial se constate), le prix
        // s'exprime à la value date (c'est le montant échangé au règlement),
        // et le remboursement final tombe à la payment date. La devise nomme
        // le calendrier de jours ouvrés qui porte tout ça.
        strike_date: p.strike_date || null,
        value_date: p.value_date || null,
        payment_date: p.payment_date || null,
        settlement_ccy: p.currency || null,
        // Repli historique : sans date de strike, l'axe reste ancré sur la
        // value date, comme avant que les trois dates existent.
        anchor: p.strike_date || p.value_date || null,
      }),
    })
    const data = await _json(res, 'Erreur calcul du prix modèle')
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
        sigma: p.underlyings?.[0]?.sigma ?? null,
        q: p.underlyings?.[0]?.q ?? null,
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
