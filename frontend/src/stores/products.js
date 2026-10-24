import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../utils/api.js'
import { durableCommand } from '../utils/commands.js'

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
  const offset = ref(0), hasMore = ref(false)
  const pageSize = 50

  async function postCommand(path, operation, payload, fallback) {
    return durableCommand(operation, payload, async key => {
      const res = await apiFetch(path, { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, command_key: key }) })
      const data = await res.json()
      if (!res.ok) throw new Error(message(data, fallback))
      if (!data?.product_id) throw new Error('Réponse incomplète ; reprenez la même commande pour vérifier son résultat.')
      return data
    })
  }

  async function getProduct(id, { termsVersion = null } = {}) {
    const res = await apiFetch(`/api/products/${id}${termsVersion == null ? '' : `?terms_version=${termsVersion}`}`)
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(message(data, 'Produit introuvable.'))
    return data
  }

  async function fetchCalculation(productId, calculationId) {
    const res = await apiFetch(`/api/products/${productId}/calculations/${calculationId}`)
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(message(data, 'Calcul conservé introuvable.'))
    return data
  }

  // Used by the library's expandable rows. It deliberately does not toggle
  // the store-wide loader, otherwise opening one row would replace the whole
  // product table with the page spinner.
  async function fetchDetails(id, { offset = null, limit = 20 } = {}) {
    if (offset != null) {
      const response = await apiFetch(`/api/products/${id}?calculations_limit=${limit}&calculations_offset=${offset}`)
      const data = await response.json()
      if (!response.ok) throw new Error(message(data, 'Dossier inaccessible.'))
      return data
    }
    return getProduct(id)
  }

  async function fetchHistory(id, offset = 0) {
    const response = await apiFetch(`/api/products/${id}/history?limit=20&offset=${offset}`)
    const data = await response.json()
    if (!response.ok) throw new Error(message(data, 'Historique inaccessible.'))
    return data
  }

  async function fetchAll({ archived = false, pageOffset = 0 } = {}) {
    loading.value = true
    error.value = ''
    try {
      const res = await apiFetch(`/api/products?archived=${archived}&paged=true&limit=${pageSize}&offset=${pageOffset}`)
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(message(data, 'Impossible de charger les produits.'))
      items.value = Array.isArray(data) ? data : data.items
      offset.value = pageOffset; hasMore.value = data.has_more === true
      return data
    } catch (e) {
      error.value = e.message
      return []
    } finally {
      loading.value = false
    }
  }

  async function fetchOne(id, { calculationId = null, termsVersion = null, withCalculation = true } = {}) {
    loading.value = true
    error.value = ''
    try {
      const data = await getProduct(id, { termsVersion })
      let calculationInput = null
      const calculation = !withCalculation ? null : calculationId == null
        ? data.calculations?.filter(item => item.terms_version === data.terms_version).at(-1)
        : data.calculations?.find(item => item.id === Number(calculationId))
      if (calculationId != null && !calculation) {
        throw new Error('Ce calcul n’appartient pas au produit ou n’existe plus.')
      }
      if (calculation && calculation.terms_version !== data.terms_version) {
        throw new Error(
          'Ce calcul porte sur une ancienne version des termes. Il reste consultable depuis la bibliothèque.')
      }
      if (calculation) {
        calculationInput = (await fetchCalculation(id, calculation.id)).input
      }
      current.value = data
      return { product: data, calculationInput, calculationId: calculation?.id ?? null,
        notice: withCalculation && !calculation ? 'Aucun calcul conservé pour cette version. Les termes sont chargés ; vérifiez les hypothèses de marché avant de calculer.' : '' }
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function retainPricing({
    name, pricingInput, pricingReceipt, intent, listed = true,
  }) {
    saving.value = true
    error.value = ''
    try {
      const data = await postCommand('/api/products', 'retain-product', {
        name,
        pricing_input: pricingInput,
        pricing_receipt: pricingReceipt || null,
        intent,
        listed,
      }, 'Le produit n’a pas pu être conservé.')
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
      const data = await postCommand(`/api/products/${product.product_id}/calculations`,
        `retain-calculation-${product.product_id}`, {
          expected_revision: product.revision,
          pricing_receipt: pricingReceipt,
        }, 'Le calcul n’a pas pu être conservé.')
      current.value = data
      return data
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      saving.value = false
    }
  }

  async function setListed(product, { listed = true, name = null } = {}) {
    saving.value = true
    error.value = ''
    try {
      const res = await apiFetch(`/api/products/${product.product_id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_revision: product.revision,
          listed,
          ...(name ? { name } : {}),
          reason: listed
            ? 'Conservation volontaire dans Mes produits.'
            : 'Retrait volontaire de Mes produits.',
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(message(data, 'La visibilité du produit n’a pas pu être modifiée.'))
      current.value = data
      return data
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      saving.value = false
    }
  }

  async function reviseTerms(product, pricingInput, reason) {
    saving.value = true; error.value = ''
    try {
      const data = await postCommand(`/api/products/${product.product_id}/terms`,
        `revise-terms-${product.product_id}`, { expected_revision: product.revision,
          pricing_input: pricingInput, reason }, 'La nouvelle version n’a pas pu être conservée.')
      current.value = data
      return data
    } catch (e) { error.value = e.message; throw e }
    finally { saving.value = false }
  }

  async function forkForBooking(product) {
    saving.value = true; error.value = ''
    try {
      return await postCommand(`/api/products/${product.product_id}/booking-forks`,
        `booking-fork-${product.product_id}`, { expected_revision: product.revision,
          expected_terms_version: product.terms_version,
          reason: 'Autre opération explicitement demandée depuis ce pricing.' },
        'La nouvelle opération n’a pas pu être préparée.')
    } catch (e) { error.value = e.message; throw e }
    finally { saving.value = false }
  }

  function release() { current.value = null }

  return {
    items, current, loading, saving, error, offset, hasMore, pageSize,
    fetchAll, fetchOne, fetchDetails, fetchCalculation, fetchHistory,
    retainPricing, retainCalculation, reviseTerms, forkForBooking, setListed, setArchived, release,
  }
})
