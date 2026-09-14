import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../utils/api.js'

function commandKey(prefix) {
  const id = globalThis.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}-${id}`
}

function message(data, fallback) {
  if (typeof data?.detail === 'string') return data.detail
  if (typeof data?.detail?.message === 'string') return data.detail.message
  return fallback
}

export const useProductsStore = defineStore('products', () => {
  const items = ref([])
  const current = ref(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')

  async function fetchAll({ archived = false } = {}) {
    loading.value = true
    error.value = ''
    try {
      const res = await apiFetch(`/api/products?archived=${archived}`)
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(message(data, 'Impossible de charger les produits.'))
      items.value = data
      return data
    } catch (e) {
      error.value = e.message
      return []
    } finally {
      loading.value = false
    }
  }

  async function fetchOne(id) {
    loading.value = true
    error.value = ''
    try {
      const res = await apiFetch(`/api/products/${id}`)
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(message(data, 'Produit introuvable.'))
      let calculationInput = null
      const calculation = data.calculations?.at(-1)
      if (calculation) {
        const calcRes = await apiFetch(`/api/products/${id}/calculations/${calculation.id}`)
        if (calcRes.ok) calculationInput = (await calcRes.json()).input
      }
      current.value = data
      return { product: data, calculationInput }
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function retainPricing({ name, pricingInput, pricingReceipt, intent }) {
    saving.value = true
    error.value = ''
    try {
      const res = await apiFetch('/api/products', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command_key: commandKey('retain-product'),
          name,
          pricing_input: pricingInput,
          pricing_receipt: pricingReceipt || null,
          intent,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(message(data, 'Le produit n’a pas pu être conservé.'))
      current.value = data
      return data
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      saving.value = false
    }
  }

  async function setArchived(product, archived) {
    const res = await apiFetch(`/api/products/${product.id}/archive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expected_revision: product.revision,
        archived,
        reason: archived ? 'Archivage depuis la bibliothèque.' : 'Restauration depuis la bibliothèque.',
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(message(data, 'Action impossible.'))
    return data
  }

  async function retainCalculation(product, pricingReceipt) {
    saving.value = true
    error.value = ''
    try {
      const res = await apiFetch(`/api/products/${product.product_id}/calculations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command_key: commandKey('retain-calculation'),
          expected_revision: product.revision,
          pricing_receipt: pricingReceipt,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(message(data, 'Le calcul n’a pas pu être conservé.'))
      current.value = data
      return data
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      saving.value = false
    }
  }

  function release() { current.value = null }

  return {
    items, current, loading, saving, error,
    fetchAll, fetchOne, retainPricing, retainCalculation, setArchived, release,
  }
})
