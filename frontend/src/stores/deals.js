import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../utils/api.js'

function errorMessage(err, fallback) {
  const detail = err?.detail
  if (!detail || typeof detail !== 'object') return detail || fallback
  const describe = failure => {
    const field = failure.field ? `Champ « ${failure.field} » — ` : ''
    const message = failure.message || failure.code || JSON.stringify(failure)
    const expected = failure.expected ? ` Attendu : ${failure.expected}` : ''
    const action = failure.action ? ` Action : ${failure.action}` : ''
    return `${field}${message}${expected}${action}`
  }
  const failures = (detail.failures || []).flatMap(f => {
    if (f.failures) return [
      f.event_date ? `Événement du ${f.event_date}` : null,
      ...f.failures.map(describe),
    ].filter(Boolean)
    return describe(f)
  })
  return [detail.message || detail.code || fallback, ...failures].join('\n')
}

export const useDealsStore = defineStore('deals', () => {
  const deals = ref([])
  const currentDeal = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const refreshStatus = ref('')
  const auditEvents = ref([])
  const pendingAmendments = ref([])

  async function loadDeals() {
    loading.value = true; error.value = null
    try {
      const res = await apiFetch('/api/deals')
      if (!res.ok) throw new Error('Erreur chargement deals')
      deals.value = await res.json()
    } catch (e) { error.value = e.message }
    finally { loading.value = false }
  }

  async function nextRef() {
    const res = await apiFetch('/api/deals/next-ref')
    if (!res.ok) return null
    return (await res.json()).reference
  }

  async function bookDeal(payload) {
    loading.value = true; error.value = null
    try {
      const res = await apiFetch('/api/deals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(errorMessage(err, 'Erreur booking'))
      }
      const deal = await res.json()
      deals.value.unshift(deal)
      currentDeal.value = deal
      return deal
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function selectDeal(id) {
    if (currentDeal.value?.id === id) return currentDeal.value
    loading.value = true; error.value = null
    try {
      const res = await apiFetch(`/api/deals/${id}`)
      if (!res.ok) throw new Error('Deal introuvable')
      currentDeal.value = await res.json()
      return currentDeal.value
    } catch (e) { error.value = e.message }
    finally { loading.value = false }
  }

  async function updateDeal(id, patch) {
    const res = await apiFetch(`/api/deals/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'Erreur')) }
    const updated = await res.json()
    const idx = deals.value.findIndex(d => d.id === id)
    if (idx >= 0) deals.value[idx] = { ...deals.value[idx], ...updated }
    if (currentDeal.value?.id === id) Object.assign(currentDeal.value, updated)
    return updated
  }

  async function updateEvent(dealId, eventId, payload) {
    const res = await apiFetch(`/api/deals/${dealId}/events/${eventId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'Erreur')) }
    const updated = await res.json()
    if (currentDeal.value?.id === dealId) await selectDeal(dealId)
    return updated
  }

  async function refreshEvents(dealId) {
    loading.value = true; refreshStatus.value = 'Chargement spots…'
    try {
      const res = await apiFetch(`/api/deals/${dealId}/events/refresh`, { method: 'POST' })
      if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'Erreur refresh')) }
      const result = await res.json()
      refreshStatus.value = `✓ ${result.message}`
      // Reload events
      const dealRes = await apiFetch(`/api/deals/${dealId}`)
      if (dealRes.ok) currentDeal.value = await dealRes.json()
      return result
    } catch (e) {
      refreshStatus.value = `⚠ ${e.message}`
      throw e
    } finally {
      loading.value = false
    }
  }

  async function validateFixing(dealId, eventId, reason) {
    const res = await apiFetch(`/api/deals/${dealId}/events/${eventId}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'Validation impossible')) }
    const updated = await res.json()
    if (currentDeal.value?.id === dealId) await selectDeal(dealId)
    return updated
  }

  async function rejectFixing(dealId, eventId, reason) {
    const res = await apiFetch(`/api/deals/${dealId}/events/${eventId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'Rejet impossible')) }
    const updated = await res.json()
    if (currentDeal.value?.id === dealId) await selectDeal(dealId)
    return updated
  }

  async function transitionProposal(dealId, proposalId, action, reason, confirmedOutcome = null) {
    const res = await apiFetch(`/api/deals/${dealId}/lifecycle-proposals/${proposalId}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason, confirmed_outcome: confirmedOutcome }),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'Transition impossible')) }
    const result = await res.json()
    currentDeal.value = null
    await selectDeal(dealId)
    return result
  }

  async function requestAmendment(dealId, payload) {
    const res = await apiFetch(`/api/deals/${dealId}/amendment-requests`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'Demande impossible')) }
    const result = await res.json()
    currentDeal.value = null
    await selectDeal(dealId)
    return result
  }

  async function transitionAmendment(dealId, requestId, action, reason) {
    const res = await apiFetch(`/api/deals/${dealId}/amendment-requests/${requestId}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'Transition impossible')) }
    const result = await res.json()
    currentDeal.value = null
    await selectDeal(dealId)
    return result
  }

  async function loadPendingAmendments() {
    const res = await apiFetch('/api/deals/amendment-requests/pending')
    if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'File checker indisponible')) }
    pendingAmendments.value = await res.json()
    return pendingAmendments.value
  }

  async function loadAudit(dealId, filters = {}) {
    const params = new URLSearchParams()
    if (filters.action) params.set('action', filters.action)
    if (filters.result) params.set('result', filters.result)
    params.set('limit', String(filters.limit || 250))
    const res = await apiFetch(`/api/deals/${dealId}/audit?${params}`)
    if (!res.ok) { const err = await res.json(); throw new Error(errorMessage(err, 'Audit indisponible')) }
    const data = await res.json()
    auditEvents.value = data.items || []
    return data
  }

  async function getRepriceInputs(dealId) {
    const res = await apiFetch(`/api/deals/${dealId}/reprice`)
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur reprice') }
    return res.json()
  }

  async function getWatchlist() {
    const res = await apiFetch('/api/deals/watchlist')
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur watchlist') }
    return res.json()
  }

  return {
    deals, currentDeal, loading, error, refreshStatus, auditEvents, pendingAmendments,
    loadDeals, nextRef, bookDeal, selectDeal, updateDeal,
    updateEvent, validateFixing, rejectFixing, transitionProposal,
    requestAmendment, transitionAmendment, loadPendingAmendments, loadAudit,
    refreshEvents, getRepriceInputs, getWatchlist,
  }
})
