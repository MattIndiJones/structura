<template>
  <div class="product-context px-5 py-2 border-b flex flex-wrap items-center gap-3">
    <template v-if="pricing.currentProduct">
      <span class="text-[10px] font-bold uppercase tracking-widest" style="color: var(--muted);">
        Produit conservé
      </span>
      <span class="font-mono text-xs font-semibold" style="color: var(--accent);">
        {{ pricing.currentProduct.reference }}
      </span>
      <span class="text-xs font-semibold truncate">{{ pricing.currentProduct.name }}</span>
      <span class="text-[10px] rounded px-2 py-0.5" style="background: var(--surface2); color: var(--muted);">
        Termes v{{ pricing.currentProduct.terms_version }} · révision {{ pricing.currentProduct.revision }}
      </span>
      <button v-if="canRetainCalculation" class="btn-secondary text-xs ml-auto"
              :disabled="products.saving" @click="retainCalculation">
        {{ products.saving ? 'Conservation…' : 'Conserver ce calcul' }}
      </button>
      <RouterLink :to="{ path: '/rfq', query: { product: pricing.currentProduct.product_id } }"
                  :class="['btn-secondary text-xs', canRetainCalculation ? '' : 'ml-auto']">
        Ouvrir une RFQ
      </RouterLink>
      <RouterLink to="/products" class="text-xs font-semibold" style="color: var(--accent);">
        Bibliothèque
      </RouterLink>
    </template>
    <template v-else>
      <div class="min-w-0">
        <div class="text-xs font-semibold">Session de pricing non conservée</div>
        <div class="text-[10px]" style="color: var(--muted);">
          La fermeture ne crée aucun dossier. La conservation reste une action volontaire.
        </div>
      </div>
      <button class="btn-secondary text-xs ml-auto" :disabled="!!pricing.parseError" @click="openRetention">
        Conserver le produit
      </button>
    </template>
  </div>

  <BaseModal v-model="modal" title="Conserver ce produit" max-width="480px">
    <div class="space-y-4">
      <label class="block">
        <span class="label">Nom du produit</span>
        <input v-model.trim="name" class="input w-full" maxlength="200" @keyup.enter="retain" />
      </label>
      <div class="rounded border px-3 py-2 text-xs leading-relaxed"
           style="border-color: var(--border); background: var(--surface2); color: var(--muted);">
        Les termes, le panier et le calendrier seront figés dans le Product.
        <span v-if="retainsCurrentPrice">Le prix affiché sera conservé avec ses entrées de calcul datées.</span>
        <span v-else-if="legacyReceipt">
          Le prix affiché utilise une ancienne preuve. Relancez le pricing pour le conserver ;
          le Product peut être conservé dès maintenant sans ce prix.
        </span>
        <span v-else>Aucun prix courant fiable ne sera attaché ; le produit pourra être repricé plus tard.</span>
      </div>
      <AlertMessage v-if="products.error" kind="error">{{ products.error }}</AlertMessage>
    </div>
    <template #footer>
      <button class="btn-secondary text-xs" :disabled="products.saving" @click="modal = false">Annuler</button>
      <button class="btn-primary text-xs" :disabled="products.saving || !name" @click="retain">
        {{ products.saving ? 'Conservation…' : 'Conserver' }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { usePricingStore } from '../stores/pricing.js'
import { useProductsStore } from '../stores/products.js'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'

const pricing = usePricingStore()
const products = useProductsStore()
const modal = ref(false)
const name = ref('')

const legacyReceipt = computed(() => !!(
  pricing.result?.pricing_receipt?.server_signature
  && pricing.result.pricing_receipt.signature_version !== 2
  && !pricing.resultIsStale
))

const retainsCurrentPrice = computed(() => !!(
  pricing.result?.pricing_receipt?.server_signature
  && pricing.result.pricing_receipt.signature_version === 2
  && !pricing.resultIsStale
))

const canRetainCalculation = computed(() => {
  if (!pricing.currentProduct || !retainsCurrentPrice.value) return false
  const calculatedAt = pricing.result?.pricing_receipt?.calculated_at
  return !pricing.currentProduct.calculations?.some(c => c.calculated_at === calculatedAt)
})

function openRetention() {
  name.value = pricing.productTitle
  products.error = ''
  modal.value = true
}

async function retain() {
  if (!name.value || products.saving) return
  const receipt = retainsCurrentPrice.value ? pricing.result.pricing_receipt : null
  const pricingInput = receipt?.pricing_input || pricing.pricingBody()
  const saved = await products.retainPricing({
    name: name.value,
    pricingInput,
    pricingReceipt: receipt,
    intent: {
      nominal: Number(pricing.globalParams.nominal) > 0 ? Number(pricing.globalParams.nominal) : null,
      side: 'BUY',
    },
  })
  pricing.currentProduct = saved
  modal.value = false
}

async function retainCalculation() {
  if (!canRetainCalculation.value || products.saving) return
  const saved = await products.retainCalculation(
    pricing.currentProduct, pricing.result.pricing_receipt)
  pricing.currentProduct = saved
}
</script>

<style scoped>
.product-context {
  border-color: var(--border);
  background: color-mix(in srgb, var(--surface2) 72%, white);
}
</style>
