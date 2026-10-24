<script setup>
import { watch, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch, apiErrorMessage } from '../utils/api'
import { formatDate, formatNumber } from '../utils/format.js'
import BackLink from '../components/ui/BackLink.vue'
import SensitiveValue from '../components/SensitiveValue.vue'

const route = useRoute()
const router = useRouter()
const review = ref(null)
const error = ref('')
const loading = ref(false)
const submitting = ref(false)
const confirmed = ref(false)
const nettingSetId = ref('')
const isOtc = computed(() => review.value?.legal_context?.transaction_format?.toUpperCase() === 'OTC')

async function load() {
  loading.value = true
  confirmed.value = false
  nettingSetId.value = ''
  error.value = ''
  review.value = null
  try {
    const response = await apiFetch(`/api/rfq/${route.params.rfqId}/booking-review`)
    if (!response.ok) throw new Error(apiErrorMessage(await response.json()))
    review.value = await response.json()
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
}

async function book() {
  if (submitting.value || !confirmed.value || !review.value) return
  submitting.value = true
  error.value = ''
  try {
    const response = await apiFetch(`/api/rfq/${route.params.rfqId}/book`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ review_token: review.value.review_token,
        ccr_netting_set_id: nettingSetId.value ? Number(nettingSetId.value) : null }),
    })
    if (!response.ok) throw new Error(apiErrorMessage(await response.json()))
    const deal = await response.json()
    await router.push({ path: '/booking', query: { deal: deal.id } })
  } catch (err) { error.value = err.message; confirmed.value = false }
  finally { submitting.value = false }
}

watch(() => route.params.rfqId, load, { immediate: true })
</script>

<template>
  <div class="booking-review">
    <BackLink fallback="/rfq">← Retour aux RFQ</BackLink>
    <h1>Revue du booking RFQ</h1>
    <p v-if="loading" role="status">Chargement du dossier…</p>
    <p v-if="error" class="review-error" role="alert">{{ error }}</p>
    <button class="btn-secondary btn-sm" :disabled="loading || submitting" @click="load">Recharger la revue</button>
    <template v-if="review">
      <h2>{{ review.reference }} — {{ review.name }}</h2>
      <dl>
        <dt>Contrepartie</dt><dd>{{ review.counterparty || 'Contrepartie à qualifier' }}</dd>
        <dt>Sens banque</dt><dd>{{ review.side === 'vente' ? 'Vente' : 'Achat' }}</dd>
        <dt>Nominal</dt><dd><SensitiveValue>{{ formatNumber(review.nominal) }}</SensitiveValue> {{ review.terms.settlement_ccy }}</dd>
        <dt>Prix retenu (%)</dt><dd><SensitiveValue>{{ formatNumber(review.price_traded, 4) }}</SensitiveValue></dd>
        <dt>Date de traitement</dt><dd>{{ formatDate(review.trade_date) }}</dd>
        <dt>Format / famille</dt><dd>{{ review.legal_context?.transaction_format || 'À qualifier' }} / {{ review.legal_context?.instrument_family || 'À qualifier' }}</dd>
        <dt>Documentation</dt><dd>{{ review.legal_context?.documentation_reference || 'Non renseignée' }}</dd>
        <dt>Strike / valeur</dt><dd>{{ formatDate(review.terms.strike_date) }} / {{ formatDate(review.terms.value_date) }}</dd>
        <dt>Maturité / paiement</dt><dd>{{ formatDate(review.terms.maturity_date) }} / {{ formatDate(review.terms.payment_date) }}</dd>
        <dt>Termes Product</dt><dd>Version {{ review.terms_version }}</dd>
        <dt>Calcul conservé</dt><dd>{{ formatDate(review.calculation.calculated_at) }}</dd>
        <dt>Empreinte des entrées</dt><dd class="fingerprint">{{ review.calculation.input_hash }}</dd>
      </dl>
      <h3>Sous-jacents</h3>
      <p>{{ review.terms.underlyings.map(u => `${u.name} (${u.ticker})`).join(', ') }}</p>
      <details><summary>Contrat PayScript et paramètres</summary><SensitiveValue mode="blur"><pre>{{ review.terms.script }}</pre><pre>{{ review.terms.parameters }}</pre><pre>{{ review.terms.resolved_events }}</pre></SensitiveValue></details>
      <form @submit.prevent="book">
        <label v-if="isOtc">Netting set OTC — accord effectif requis
          <input v-model="nettingSetId" type="number" min="1" step="1" class="input" required :disabled="submitting" />
        </label>
        <p v-if="isOtc">L’accord doit être actif à la date de traitement, couvrir ce produit et cette devise, et porter le CSA requis par la relation bilatérale.</p>
        <label class="confirmation"><input v-model="confirmed" type="checkbox" :disabled="submitting" />J’ai vérifié le contrat, la réponse retenue et la preuve de calcul conservée.</label>
        <p>Le booking applique les contrôles de contrat, de cotation, de crédit et d’unicité. Si le dossier change, rechargez cette revue.</p>
        <button class="btn-primary" :disabled="!confirmed || submitting || !review.counterparty">{{ submitting ? 'Booking en cours…' : 'Confirmer le booking' }}</button>
      </form>
    </template>
  </div>
</template>

<style scoped>
.booking-review { max-width: 1000px; margin: 0 auto; padding: 20px; }
dl { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 6px 16px; }
dt { color: var(--text-muted, #64748b); } dd { margin: 0; }
.fingerprint { overflow-wrap: anywhere; font-family: monospace; }
pre { overflow: auto; max-height: 260px; white-space: pre-wrap; }
form { margin-top: 20px; } label { display: block; margin: 12px 0; }
.input { max-width: 160px; margin-left: 12px; }
.confirmation { display: flex; gap: 8px; align-items: center; }
.review-error { color: #b91c1c; }
@media (max-width: 600px) { dl { grid-template-columns: 1fr; } dd { margin-bottom: 8px; } }
</style>
