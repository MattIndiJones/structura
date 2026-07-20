import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../utils/api.js'

export const useDealsStore = defineStore('deals', () => {
  const deals = ref([])
  const currentDeal = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const refreshStatus = ref('')

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
        throw new Error(err.detail || 'Erreur booking')
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
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur') }
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
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur') }
    const updated = await res.json()
    if (currentDeal.value?.events) {
      const idx = currentDeal.value.events.findIndex(e => e.id === eventId)
      if (idx >= 0) currentDeal.value.events.splice(idx, 1, updated)
    }
    return updated
  }

  async function refreshEvents(dealId) {
    loading.value = true; refreshStatus.value = 'Chargement spots…'
    try {
      const res = await apiFetch(`/api/deals/${dealId}/events/refresh`, { method: 'POST' })
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur refresh') }
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
    deals, currentDeal, loading, error, refreshStatus,
    loadDeals, nextRef, bookDeal, selectDeal, updateDeal,
    updateEvent, refreshEvents, getRepriceInputs, getWatchlist,
  }
})
