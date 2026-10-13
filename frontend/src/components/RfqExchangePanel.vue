<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRfqStore } from '../stores/rfq.js'
import AlertMessage from './ui/AlertMessage.vue'
import RfqPricingPanel from './RfqPricingPanel.vue'
import RfqTransportStatus from './RfqTransportStatus.vue'
import { formatDate, formatDateTime, formatNumber } from '../utils/format.js'

const props = defineProps({ rfq: { type: Object, required: true }, providers: { type: Array, default: () => [] },
  pricing: { type: Object, default: null }, calculating: Boolean, canPrice: { type: Boolean, default: true }, canPrepare: { type: Boolean, default: true }, pricingError: { type: String, default: '' } })
const emit = defineEmits(['calculate', 'pricer', 'new-round'])
const store = useRfqStore()
const title = ref('')
const deadline = ref('')
const providerIds = ref([])
const relationshipIds = ref([])
const recipients = ref([])
const excludedRecipients = ref([])
const recipientLoading = ref(false)
const recipientError = ref('')
const preview = ref(null)
const loading = ref(false)
const error = ref('')
const mobileTab = ref('request')
const tracking = ref(null)
const sending = ref(false)
const sent = ref(false)
let commandKey = null
const frozen = computed(() => tracking.value?.round)
const roundClosed = computed(() => frozen.value?.state !== 'OPEN' || ['clos', 'sans_suite'].includes(props.rfq.status))
const alreadySent = recipient => tracking.value?.deliveries.some(item => item.recipient.organization_id === recipient.partner_entity_id)
let generation = 0
let recipientGeneration = 0
let trackingTimer
onMounted(() => { trackingTimer = setInterval(() => { if (!document.hidden && !sending.value && tracking.value?.deliveries.some(item => item.transport)) loadTracking() }, 5000) })
onUnmounted(() => clearInterval(trackingTimer))
const valid = computed(() => !!title.value.trim() && !!deadline.value && providerIds.value.length + relationshipIds.value.length > 0)
const request = computed(() => preview.value?.request || frozen.value?.request)
const source = computed(() => preview.value?.source || { product_reference: request.value?.product_reference })
const nominal = value => formatNumber(value, 0)
function reset() {
  generation++
  preview.value = null
  loading.value = false
  error.value = ''
  tracking.value = null
  sending.value = false
  sent.value = false
  title.value = props.rfq.payoff_family || 'Produit structuré'
  const date = new Date(Date.now() + 15 * 60_000)
  deadline.value = new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
  providerIds.value = []
  relationshipIds.value = []
  loadRecipients()
  loadTracking()
}
async function loadTracking() {
  const id = props.rfq.id
  try {
    const data = await store.fetchExchange(id)
    if (id !== props.rfq.id) return
    tracking.value = data
    if (data.round) {
      title.value = data.round.request.title
      const value = data.round.request.response_deadline
      if (value) {
        const date = new Date(value)
        deadline.value = new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
      } else deadline.value = ''
    }
  } catch (failure) { if (id === props.rfq.id) error.value = failure.message }
}
async function loadRecipients() {
  const ticket = ++recipientGeneration
  recipients.value = []
  excludedRecipients.value = []
  recipientError.value = ''
  recipientLoading.value = false
  if (!props.rfq.pilot_desk_id) return
  recipientLoading.value = true
  try {
    const data = await store.fetchRecipients(props.rfq.id)
    if (ticket === recipientGeneration) { recipients.value = data.eligible; excludedRecipients.value = data.excluded }
  } catch (failure) { if (ticket === recipientGeneration) recipientError.value = failure.message }
  finally { if (ticket === recipientGeneration) recipientLoading.value = false }
}
watch([() => props.rfq.id, () => props.rfq.product_terms_version], reset, { immediate: true })
watch([title, deadline, providerIds, relationshipIds], () => { generation++; preview.value = null; loading.value = false; error.value = '' }, { deep: true })
async function prepare() {
  const ticket = ++generation
  loading.value = true
  error.value = ''
  try {
    const result = await store.previewExchange(props.rfq, { sharedTitle: title.value.trim(),
      deadline: frozen.value?.request.response_deadline || new Date(deadline.value).toISOString(), providerIds: [...providerIds.value], relationshipIds: [...relationshipIds.value] })
    if (generation === ticket) preview.value = result
    if (generation === ticket) commandKey = crypto.randomUUID()
  } catch (failure) {
    if (generation === ticket) error.value = failure.message
  } finally { if (generation === ticket) loading.value = false }
}
async function send() {
  if (!preview.value || sending.value) return
  const id = props.rfq.id
  const packet = preview.value
  sending.value = true
  error.value = ''
  try {
    const result = await store.sendExchange(id, { expected_terms_version: packet.source.terms_version,
      shared_title: packet.request.title, response_deadline: packet.request.response_deadline,
      provider_ids: [], relationship_ids: packet.messages.filter(item => item.recipient_type === 'NETWORK').map(item => item.recipient_id),
      expected_preview_hash: packet.preview_hash, command_key: commandKey })
    if (props.rfq.id !== id) return
    tracking.value = result.tracking
    relationshipIds.value = []
    preview.value = null
    sent.value = true
    await store.fetchOne(id)
  } catch (failure) { if (props.rfq.id === id) error.value = failure.message }
  finally { if (props.rfq.id === id) sending.value = false }
}
</script>

<template>
  <div class="exchange-panel">
    <section class="exchange-config space-y-3" aria-label="Préparation de la demande partagée">
      <div class="flex items-center justify-between gap-2 flex-wrap text-xs">
        <strong>{{ rfq.reference }}</strong><span>Product lié · termes v{{ rfq.product_terms_version }}</span>
        <button v-if="canPrice" class="btn-secondary btn-sm" :disabled="calculating" @click="$emit('pricer')">Ouvrir dans le Pricer</button>
      </div>
      <AlertMessage kind="info">Préparez le récapitulatif puis envoyez aux partenaires choisis. La demande sera enregistrée dans leur desk Structura ; les termes et le délai du tour seront figés.</AlertMessage>
      <AlertMessage v-if="sent" kind="success">Envoi enregistré. Le suivi distingue la réception confirmée, la lecture et la réponse de prix ; les échanges distants reprennent automatiquement après interruption.</AlertMessage>
      <div v-if="frozen" class="text-xs flex flex-wrap gap-2 items-center"><strong>{{ frozen.exchange_reference }} · tour {{ frozen.number }} · {{ frozen.state === 'SUPERSEDED' ? 'tour remplacé' : roundClosed ? 'tour clôturé' : 'termes figés' }}</strong><button v-if="canPrepare && !roundClosed" class="btn-ghost btn-sm" @click="emit('new-round')">Ouvrir un nouveau tour</button><button class="btn-ghost btn-sm" @click="loadTracking">Actualiser le suivi</button></div>
      <AlertMessage v-if="frozen && !frozen.request.response_deadline" kind="warning">Ce tour manuel a été figé sans délai publié. Ouvrez un nouveau tour pour envoyer une demande réseau avec son délai explicite.</AlertMessage>
      <div class="grid sm:grid-cols-2 gap-3">
        <label><span class="label">Intitulé partagé · distinct du nom interne</span><input v-model="title" :disabled="!!frozen || sending" class="input w-full" maxlength="200" /></label>
        <label><span class="label">Limite de réponse · heure locale</span><input v-model="deadline" :disabled="!!frozen || sending" type="datetime-local" class="input w-full" /><span class="text-[10px] text-slate-400">{{ frozen ? 'Délai du tour figé.' : 'Proposition de 15 min, modifiable.' }}</span></label>
      </div>
      <fieldset v-if="rfq.pilot_desk_id"><legend class="label">Partenaires RFQ autorisés de votre organisation</legend>
        <p v-if="recipientLoading" class="text-xs text-slate-500">Chargement des partenaires…</p>
        <AlertMessage v-if="recipientError" kind="error">{{ recipientError }}</AlertMessage>
        <div class="recipient-list flex flex-wrap gap-3 mt-1"><label v-for="recipient in recipients" :key="recipient.id" class="text-xs flex items-center gap-2">
          <input v-model="relationshipIds" type="checkbox" :value="recipient.id" :disabled="sending || alreadySent(recipient) || frozen?.state && frozen.state !== 'OPEN'" />{{ recipient.label }} · {{ recipient.desk_name }}<span v-if="alreadySent(recipient)" class="text-slate-500">(envoi enregistré)</span><span v-else-if="!recipient.treatment_allowed" class="text-slate-500">(prix uniquement)</span>
        </label><span v-if="!recipientLoading && !recipients.length" class="text-xs text-slate-400">Aucun partenaire autorisé pour les termes de cette RFQ.</span></div>
        <details v-if="excludedRecipients.length" class="text-xs mt-2"><summary class="cursor-pointer">Partenaires exclus de ce périmètre</summary><div v-for="recipient in excludedRecipients" :key="recipient.id" class="mt-1">{{ recipient.label }} · {{ recipient.issues.join(' ; ') }}</div></details>
      </fieldset>
      <fieldset><legend class="label">Fournisseurs pour le parcours manuel</legend>
        <div class="recipient-list flex flex-wrap gap-3 mt-1"><label v-for="provider in providers" :key="provider.id" class="text-xs flex items-center gap-2">
          <input v-model="providerIds" type="checkbox" :value="provider.id" :disabled="sending" />{{ provider.label }}
        </label><span v-if="!providers.length" class="text-xs text-slate-400">Aucun fournisseur disponible dans le référentiel.</span></div>
      </fieldset>
      <div class="flex flex-wrap gap-2"><button class="btn-primary btn-sm" :disabled="!valid || loading || sending" @click="prepare">{{ loading ? 'Préparation…' : 'Préparer le récapitulatif' }}</button>
        <button v-if="preview && relationshipIds.length" class="btn-primary btn-sm" :disabled="sending || preview.issues.length > 0 || providerIds.length > 0" @click="send">{{ sending ? 'Envoi…' : 'Envoyer la RFQ' }}</button>
        <span v-if="preview && providerIds.length && relationshipIds.length" class="text-xs">Pour envoyer, sélectionnez uniquement les partenaires réseau. Les fournisseurs manuels restent saisis dans la RFQ.</span>
        <button v-if="canPrice" class="btn-secondary btn-sm" :disabled="calculating || !!rfq.booked_deal" @click="$emit('calculate')">{{ calculating ? 'Calcul en cours…' : 'Calculer avec le moteur actuel' }}</button></div>
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <AlertMessage v-if="pricingError" kind="error">{{ pricingError }}</AlertMessage>
    </section>
    <div class="flex gap-2 lg:hidden shrink-0" role="group" aria-label="Panneau de consultation">
      <button class="btn-ghost btn-sm" :aria-pressed="mobileTab === 'request'" @click="mobileTab = 'request'">Demande commune</button>
      <button v-if="canPrice" class="btn-ghost btn-sm" :aria-pressed="mobileTab === 'pricing'" @click="mobileTab = 'pricing'">Pricing privé</button>
    </div>
    <div class="exchange-columns" :class="{ 'exchange-columns--single': !canPrice }">
      <section :class="['exchange-scroll space-y-3', mobileTab !== 'request' ? 'hidden lg:block' : '']" aria-label="Contenu partagé depuis Product">
        <section v-if="tracking?.deliveries.length" class="card space-y-2"><h3 class="font-semibold text-sm">Suivi par destinataire</h3><div class="table-shell overflow-x-auto"><table><thead><tr><th>Destinataire</th><th>Livraison</th><th>Lecture</th><th>Réponse</th></tr></thead><tbody><tr v-for="item in tracking.deliveries" :key="item.id"><td>{{ item.recipient.organization }}<div class="text-xs text-slate-500">{{ item.recipient.desk }}</div></td><td><RfqTransportStatus v-if="item.transport" :transport="item.transport" :can-retry="rfq.access_rights?.includes('solicit')" @updated="loadTracking" /><span v-else>{{ formatDateTime(item.delivered_at) }}</span></td><td>{{ item.read_at ? formatDateTime(item.read_at) : 'Pas encore lue' }}</td><td>{{ roundClosed || item.business_status === 'ROUND_CLOSED' ? 'Tour clôturé' : item.business_status === 'QUOTE_RECEIVED' ? 'Prix reçu' : 'Prix en attente' }}</td></tr></tbody></table></div></section>
        <p v-if="!request" class="text-sm text-slate-400">Choisissez les fournisseurs et préparez le récapitulatif. Les termes ne sont pas ressaisis.</p>
        <template v-else>
          <div class="card space-y-2 text-xs"><strong>{{ request.title }}</strong><p>{{ request.requester.organization || 'Organisation à renseigner' }} · {{ request.side === 'BUY' ? 'Achat du demandeur' : 'Vente du demandeur' }} · {{ nominal(request.nominal) }} {{ request.currency }}</p>
            <p>Prix demandé en % du nominal, all-in · limite {{ formatDateTime(request.response_deadline) }}.</p>
            <p>{{ source.product_reference }} · termes v{{ request.terms_version }} · empreinte <span class="font-mono break-all">{{ request.terms_fingerprint }}</span></p>
          </div>
          <AlertMessage v-if="preview?.issues.length" kind="warning"><ul class="list-disc pl-4"><li v-for="issue in preview.issues" :key="issue">{{ issue }}</li></ul></AlertMessage>
          <section class="card space-y-3"><h3 class="font-semibold text-sm">Termes communs</h3>
            <dl class="grid grid-cols-2 gap-2 text-xs"><dt>Strike</dt><dd>{{ formatDate(request.terms.strike_date) || '—' }}</dd><dt>Valeur</dt><dd>{{ formatDate(request.terms.value_date) || '—' }}</dd><dt>Maturité</dt><dd>{{ formatDate(request.terms.maturity_date) || '—' }}</dd><dt>Paiement</dt><dd>{{ formatDate(request.terms.payment_date) || '—' }}</dd></dl>
            <div class="table-shell overflow-x-auto"><table><thead><tr><th>Paramètre effectif</th><th>Valeur</th></tr></thead><tbody><tr v-for="parameter in request.terms.parameters" :key="parameter.name"><td>{{ parameter.name }}</td><td>{{ JSON.stringify(parameter.value) }}{{ parameter.is_pct ? ' (fraction de pourcentage)' : '' }}</td></tr></tbody></table></div>
            <p class="text-xs">Panier : {{ request.terms.underlyings.map(item => `${item.name} (${item.ticker}, ${item.ccy})`).join(' · ') }}</p>
            <details><summary class="text-xs cursor-pointer font-semibold">Script et calendrier contractuels</summary><pre class="shared-payload mt-2">{{ request.terms.script }}</pre><pre class="shared-payload mt-2">{{ JSON.stringify(request.terms.resolved_events || request.terms.schedule, null, 2) }}</pre></details>
          </section>
          <section v-if="preview" class="card space-y-2"><h3 class="font-semibold text-sm">Projection individuelle par fournisseur</h3>
            <details v-for="message in preview.messages" :key="`${message.recipient_type || 'MANUAL'}-${message.recipient_id}`"><summary class="text-xs cursor-pointer">{{ message.request.recipient.provider || message.request.recipient.organization }} · {{ message.recipient_type === 'NETWORK' ? 'partenaire RFQ' : 'manuel' }} · contenu partagé</summary><pre class="shared-payload mt-2">{{ JSON.stringify(message.request, null, 2) }}</pre></details>
            <p class="text-xs text-slate-400">Chaque projection contient les termes et son destinataire. Les marchés, modèles, calculs, autres fournisseurs et données CRM restent privés.</p>
          </section>
        </template>
      </section>
      <section v-if="canPrice" :class="['exchange-scroll', mobileTab !== 'pricing' ? 'hidden lg:block' : '']" aria-label="Contrôle du prix privé">
        <RfqPricingPanel :rfq="rfq" :pricing="pricing" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.exchange-panel { height: 100%; min-height: 0; display: flex; flex-direction: column; gap: 1rem; overflow: hidden; }
.exchange-config { flex: 0 1 auto; max-height: 55%; min-height: 0; overflow: auto; overscroll-behavior: contain; }
.recipient-list { max-height: 4.5rem; overflow-y: auto; overscroll-behavior: contain; }
.exchange-columns { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr); overflow: hidden; gap: 1rem; }
.exchange-scroll { min-height: 0; min-width: 0; overflow: auto; overscroll-behavior: contain; padding-right: .25rem; scrollbar-gutter: stable; }
.shared-payload { font-size: .7rem; white-space: pre-wrap; overflow-wrap: anywhere; background: var(--surface2); padding: .65rem; border-radius: var(--radius-sm); }
@media (min-width: 1024px) { .exchange-columns { grid-template-columns: minmax(0, 1fr) minmax(280px, .65fr); } }
@media (min-width: 1024px) { .exchange-columns--single { grid-template-columns: minmax(0, 1fr); } }
</style>
