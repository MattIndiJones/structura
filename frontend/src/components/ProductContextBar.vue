<template>
  <div class="product-context px-5 py-2 border-b flex flex-wrap items-center gap-3">
    <div v-if="receivedRfq" class="w-full text-xs flex flex-wrap items-center gap-2"><strong>RFQ reçue · pricing privé bancaire</strong><span>Termes reçus figés. Marchés et modèle propres à la banque.</span><RouterLink :to="{ path: '/rfq/recues', query: { open: receivedRfq } }" class="btn-secondary btn-sm ml-auto">Revenir à la RFQ reçue</RouterLink><p class="w-full text-[11px]" style="color: var(--muted)">Le dernier calcul privé est réutilisé à la réouverture. Au premier calcul, contrôlez les hypothèses initiales dans Marché. « Conserver ce calcul privé » l’enregistre pour le desk ; la publication du prix sera une action distincte.</p></div>
    <template v-if="pricing.currentProduct">
      <span class="text-[10px] font-bold uppercase tracking-widest" style="color: var(--muted);">
        {{ pricing.currentProduct.listed ? 'Produit conservé' : 'Produit interne' }}
      </span>
      <span class="font-mono text-xs font-semibold" style="color: var(--accent);">
        {{ pricing.currentProduct.reference }}
      </span>
      <span class="text-xs font-semibold truncate">{{ pricing.currentProduct.name }}</span>
      <RouterLink v-if="pricing.currentProduct.origin_product_id"
                  :to="`/products/${pricing.currentProduct.origin_product_id}/pricer`"
                  class="text-xs underline">Dossier d’origine #{{ pricing.currentProduct.origin_product_id }}</RouterLink>
      <span class="text-[10px] rounded px-2 py-0.5" style="background: var(--surface2); color: var(--muted);">
        Termes v{{ pricing.currentProduct.terms_version }} · révision {{ pricing.currentProduct.revision }}
      </span>
      <button v-if="canEditTerms && !pricing.editingProductTerms" class="btn-secondary text-xs"
              @click="pricing.beginProductTermsEdit()">Modifier les termes</button>
      <template v-if="pricing.editingProductTerms">
        <input v-model.trim="termsReason" class="input text-xs" aria-label="Motif de la nouvelle version" placeholder="Motif de la nouvelle version" />
        <button class="btn-primary text-xs" :disabled="products.saving || termsReason.length < 3" @click="saveTerms">Conserver la nouvelle version</button>
        <button class="btn-secondary text-xs" :disabled="products.saving" @click="cancelTerms">Annuler les modifications</button>
        <span class="text-xs">Copie de travail : sauvegardez la version avant calcul ou RFQ.</span>
      </template>
      <button v-if="canRetainCalculation" class="btn-secondary text-xs ml-auto"
              :disabled="products.saving" @click="retainCalculation">
        {{ products.saving ? 'Conservation…' : receivedRfq ? 'Conserver ce calcul privé' : 'Conserver ce calcul' }}
      </button>
      <button v-if="!receivedRfq && !pricing.currentProduct.listed && !pricing.editingProductTerms" class="btn-secondary text-xs"
              :class="canRetainCalculation ? '' : 'ml-auto'"
              :disabled="products.saving" @click="openRetention">
        Conserver le produit
      </button>
      <RouterLink v-if="!receivedRfq && !pricing.editingProductTerms" :to="{ path: '/rfq', query: { product: pricing.currentProduct.product_id } }"
                  :class="['btn-secondary text-xs', canRetainCalculation || !pricing.currentProduct.listed ? '' : 'ml-auto']">
        Ouvrir une RFQ
      </RouterLink>
      <RouterLink v-if="!receivedRfq" to="/products" class="text-xs font-semibold" style="color: var(--accent);">
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
      <button class="btn-secondary text-xs"
              :disabled="!!pricing.parseError || products.saving"
              @click="openDirectRfq">
        {{ products.saving ? 'Préparation…' : 'Ouvrir une RFQ' }}
      </button>
      <span v-if="products.error" class="text-xs" style="color: var(--danger);">
        {{ products.error }}
      </span>
    </template>
    <p v-if="pricing.productLoadNotice" class="w-full text-xs" role="status">{{ pricing.productLoadNotice }}</p>
    <p v-if="products.error && pricing.currentProduct" class="w-full text-xs" role="alert">{{ products.error }}</p>
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
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { usePricingStore } from '../stores/pricing.js'
import { useProductsStore } from '../stores/products.js'
import { useAuthStore } from '../stores/auth.js'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'

const pricing = usePricingStore()
const products = useProductsStore()
const router = useRouter()
const route = useRoute()
const receivedRfq = computed(() => Number(route.query.receivedRfq) || null)
const modal = ref(false)
const name = ref('')
const termsReason = ref('')
const auth = useAuthStore()
const canEditTerms = computed(() => !receivedRfq.value && !pricing.currentProduct?.execution && !pricing.openedDeal
  && !pricing.currentRfqId && !auth.readOnly && (auth.user?.installation
    ? auth.user.capabilities?.includes('business.prepare') : ['admin', 'organization_admin', 'user'].includes(auth.user?.role)))

async function saveTerms() {
  try {
    if (!await pricing.validateScript()) throw new Error('Validez le script avant de conserver les termes.')
    const input = pricing.draftProductBody(), before = JSON.stringify(input)
    const target = pricing.currentProduct, previousVersion = target.terms_version
    const product = await products.reviseTerms(target, input, termsReason.value)
    if (pricing.currentProduct !== target) {
      products.error = 'La version a été conservée sur son dossier d’origine ; le dossier actuellement affiché est inchangé.'
      return
    }
    const newerEdits = JSON.stringify(pricing.draftProductBody()) !== before
    pricing.currentProduct = product; pricing.editingProductTerms = newerEdits
    if (!newerEdits) termsReason.value = ''
    pricing.productLoadNotice = newerEdits
      ? 'Version conservée. Des saisies plus récentes restent en copie de travail : conservez-les avant de calculer.'
      : product.terms_version === previousVersion ? 'Termes inchangés : aucune nouvelle version créée.'
        : 'Version conservée. Les calculs antérieurs restent rattachés à leurs termes ; relancez le pricing.'
  } catch (e) { products.error = e.message }
}
async function cancelTerms() {
  try { await pricing.loadFromProduct(pricing.currentProduct); termsReason.value = '' }
  catch (e) { products.error = e.message }
}

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
  if (pricing.currentProduct && !pricing.currentProduct.listed) {
    let saved = pricing.currentProduct
    if (receipt && canRetainCalculation.value) {
      saved = await products.retainCalculation(saved, receipt)
    }
    saved = await products.setListed(saved, { listed: true, name: name.value })
    pricing.currentProduct = saved
    modal.value = false
    return
  }
  const pricingInput = receipt?.pricing_input || pricing.draftProductBody()
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

async function openDirectRfq() {
  if (products.saving || pricing.parseError) return
  try {
    const receipt = retainsCurrentPrice.value ? pricing.result.pricing_receipt : null
    const product = await products.retainPricing({
      name: pricing.productTitle,
      pricingInput: receipt?.pricing_input || pricing.pricingBody(),
      pricingReceipt: receipt,
      listed: false,
      intent: {
        nominal: Number(pricing.globalParams.nominal) > 0
          ? Number(pricing.globalParams.nominal) : null,
        side: 'BUY',
      },
    })
    pricing.currentProduct = product
    await router.push({ path: '/rfq', query: { product: product.product_id } })
  } catch {
    // Le store expose déjà le message précis dans la barre de contexte.
  }
}
</script>

<style scoped>
.product-context {
  border-color: var(--border);
  background: color-mix(in srgb, var(--surface2) 72%, white);
}
</style>
