<template>
  <!-- Resume the in-memory session unless another product was requested. -->
  <Pricer v-if="ready" />
  <div v-else class="flex-1 flex items-center justify-center text-slate-500 text-sm">
    Chargement…
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import Pricer from './Pricer.vue'
import { usePricingStore } from '../stores/pricing.js'
import { useAuthStore } from '../stores/auth.js'
import { useProductsStore } from '../stores/products.js'
import { useDealsStore } from '../stores/deals.js'
import { useRfqStore } from '../stores/rfq.js'
import { findProductModel } from '../utils/productModels.js'
import { openPricingSession } from '../utils/pricingSession.js'
import { apiFetch } from '../utils/api.js'

const route  = useRoute()
const store  = usePricingStore()
const auth   = useAuthStore()
const products = useProductsStore()
const deals = useDealsStore()
const rfqs = useRfqStore()
const ready  = ref(false)

async function charger() {
  if (!/^\/(pricer(?:\/|$)|products\/[^/]+\/pricer$)/.test(route.path)) return
  await openPricingSession(store, route, async () => {
  const { id, variantId, productId } = route.params
  if (productId) {
    await loadProductFromDb(parseInt(productId), route.query.calculation)
  } else if (variantId) {
    await loadVariantFromDb(parseInt(variantId))
  } else if (id) {
    await loadScriptFromDb(parseInt(id))
  } else if (route.query.dealId) {
    const deal = await deals.selectDeal(Number(route.query.dealId))
    if (deal) {
      await store.loadFromDeal(deal)
      if (!deal.product_id) {
        store.error = 'Ce deal ne possède pas de Product canonique.'
      } else {
        const loaded = await products.fetchOne(deal.product_id)
        if (loaded) store.currentProduct = loaded.product
        else store.error = 'Le Product canonique de ce deal ne peut pas être chargé.'
      }
    }
    store.leftTab = route.query.tab === 'script' ? 'script' : 'events'
  } else if (route.query.fromRfq) {
    const rfq = await rfqs.fetchOne(Number(route.query.fromRfq))
    if (rfq) {
      await store.loadFromRfq(rfq)
      if (!rfq.product_id) store.error = 'Cette RFQ ne possède pas de Product canonique.'
      else {
        const loaded = await products.fetchOne(rfq.product_id)
        if (loaded) store.currentProduct = loaded.product
      }
    }
    store.leftTab = 'deal'
  } else if (findProductModel(route.query.modele)) {
    await store.loadFromProductModel(findProductModel(route.query.modele), {
      underlyingCount: route.query.sousJacents ? Number(route.query.sousJacents) : null,
      tenorCode: route.query.tenor || null,
    })
    store.leftTab = 'script'
  } else {
    store.resetToDefaults()
  }
  })
  ready.value = true
}

onMounted(charger)

// Vue Router RÉUTILISE le composant quand deux routes le partagent : passer de
// /pricer/5 à /pricer/v/3 ne remonte rien, donc onMounted ne rejoue pas. Sans
// ce watch, cliquer « Origine » ou une autre déclinaison changeait l'URL et
// laissait l'écran sur le produit précédent — et créer une variante n'ouvrait
// jamais la variante créée.
watch(() => [route.params.id, route.params.variantId, route.params.productId,
             route.query.calculation, route.query.dealId, route.query.fromRfq,
             route.query.modele, route.query.sousJacents, route.query.tenor], async () => {
  if (!/^\/(pricer(?:\/|$)|products\/[^/]+\/pricer$)/.test(route.path)) return
  ready.value = false
  await charger()
})

async function loadProductFromDb(id, requestedCalculationId = null) {
  const parsedCalculationId = Number.parseInt(String(requestedCalculationId || ''), 10)
  const loaded = await products.fetchOne(id, {
    calculationId: Number.isFinite(parsedCalculationId) ? parsedCalculationId : null,
  })
  if (!loaded) { store.resetToDefaults(); return }
  await store.loadFromProduct(loaded.product, loaded.calculationInput)
}

async function loadVariantFromDb(id) {
  // Le contexte arrive déjà résolu — parent + delta, et pour une note neuve,
  // dates déjà recalées. Le refaire ici ferait diverger l'écran du prix.
  try {
    const res = await apiFetch(`/api/db/scripts/variants/${id}/resolved`,
                               { headers: auth.authHeaders() })
    if (!res.ok) { store.resetToDefaults(); return }
    await store.loadVariant(await res.json())
  } catch {
    store.resetToDefaults()
  }
}

async function loadScriptFromDb(id) {
  try {
    const res = await apiFetch(`/api/db/scripts/${id}`, { headers: auth.authHeaders() })
    if (!res.ok) { store.resetToDefaults(); return }
    const data = await res.json()
    await store.loadFromDb(data)
  } catch {
    store.resetToDefaults()
  }
}
</script>
