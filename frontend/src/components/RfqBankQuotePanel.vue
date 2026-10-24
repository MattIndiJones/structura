<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'
import { formatNumber, formatDateTime } from '../utils/format.js'
import { publicationStateLabel } from '../utils/rfqQuoteStates.js'
import AlertMessage from './ui/AlertMessage.vue'
import RfqTransportStatus from './RfqTransportStatus.vue'

const props = defineProps({ received: { type: Object, required: true }, contextRevision: { type: Number, required: true } })
const emit = defineEmits(['updated'])
const auth = useAuthStore()
const busy = ref(false)
const error = ref('')
const showPolicy = ref(false)
const showEditor = ref(false)
const policy = reactive({ second_validation_required: false, max_calculation_age_minutes: '', reason: '' })
const form = reactive({ calculation_id: null, price: '', firmness: 'INDICATIVE', valid_until: '',
  conditions_type: 'NONE', conditions: [], issuer_name: '', guarantor_name: '', documentation_reference: '', comment: '' })
const rights = computed(() => props.received.rights || [])
const executionFrozen = computed(() => ['RECEIVED', 'CONFIRMED'].includes(props.received.electronic_execution?.state))
const canPrepare = computed(() => rights.value.includes('prepare') && rights.value.includes('price')
  && props.received.case?.responsible_user_id === auth.user?.id && props.received.open_for_work && !executionFrozen.value)
const draft = computed(() => props.received.quote_draft)
const publications = computed(() => props.received.publications || [])
const canValidate = computed(() => rights.value.includes('validate_quote') && draft.value && !draft.value.published
  && props.received.open_for_work && !executionFrozen.value && (!props.received.publication_policy.second_validation_required || draft.value.prepared_by !== auth.user?.id))
const withdrawal = reactive({ id: null, reason: '' })
let deliveryTimer
let active = true
const current = (id, ticket) => active && props.received.id === id && props.contextRevision === ticket
onMounted(() => { deliveryTimer = setInterval(() => { if (!document.hidden && !busy.value && !showEditor.value && !showPolicy.value && !withdrawal.id && publications.value.some(p => p.transport || p.withdrawal_transport)) refresh() }, 5000) })
onUnmounted(() => { active = false; clearInterval(deliveryTimer) })
watch(() => [props.received.id, props.contextRevision], () => { busy.value = false; error.value = '' }, { flush: 'sync' })
const priceValue = computed(() => Number(String(form.price).replace(/\s/g, '').replace(',', '.')))
const toLocal = value => {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 19)
}
watch(() => [props.received.id, props.contextRevision, draft.value?.revision], () => {
  showEditor.value = false
  error.value = ''
  Object.assign(policy, { ...props.received.publication_policy, max_calculation_age_minutes: props.received.publication_policy.max_calculation_age_minutes ?? '', reason: '' })
  const payload = draft.value?.response
  Object.assign(form, { calculation_id: draft.value?.calculation_id ?? props.received.case?.calculations?.at(-1)?.id ?? null,
    price: payload?.price == null ? '' : formatNumber(payload.price, 4), firmness: payload?.firmness || 'INDICATIVE',
    valid_until: toLocal(payload?.valid_until), conditions_type: payload?.conditions_type || 'NONE',
    conditions: (payload?.conditions || []).map(row => ({ ...row })), issuer_name: payload?.issuer_name || '',
    guarantor_name: payload?.guarantor_name || '', documentation_reference: payload?.documentation_reference || '', comment: payload?.comment || '' })
}, { immediate: true })

async function action(path, method, payload) {
  const id = props.received.id, ticket = props.contextRevision
  busy.value = true
  error.value = ''
  try {
    const response = await apiFetch(`/api/rfq-inbox/${id}/${path}`, {
      method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    })
    const data = await response.json()
    if (!current(id, ticket)) return false
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.message || 'La réponse bancaire ne peut pas être traitée.')
    emit('updated', data, ticket)
    return true
  } catch (failure) { if (current(id, ticket)) error.value = failure.message; return false }
  finally { if (current(id, ticket)) busy.value = false }
}
async function refresh() {
  const id = props.received.id, ticket = props.contextRevision
  busy.value = true
  error.value = ''
  try {
    const response = await apiFetch(`/api/rfq-inbox/${id}`)
    const data = await response.json()
    if (!current(id, ticket)) return
    if (!response.ok) throw new Error(data.detail?.message || data.detail || 'Le contrôle bancaire ne peut pas être actualisé.')
    emit('updated', data, ticket)
  } catch (failure) { if (current(id, ticket)) error.value = failure.message }
  finally { if (current(id, ticket)) busy.value = false }
}
async function savePolicy() {
  if (await action('publication-policy', 'PUT', { expected_version: props.received.publication_policy.version,
    second_validation_required: policy.second_validation_required, max_calculation_age_minutes: Number(policy.max_calculation_age_minutes),
    reason: policy.reason.trim() })) showPolicy.value = false
}
async function saveDraft() {
  if (await action('quote-draft', 'PUT', { ...form, price: priceValue.value, valid_until: new Date(form.valid_until).toISOString(),
    conditions: form.conditions_type === 'NONE' ? [] : form.conditions,
    expected_revision: draft.value?.revision || 0 })) showEditor.value = false
}
const decision = () => ({ expected_revision: draft.value.revision, expected_payload_hash: draft.value.payload_hash })
async function withdraw() {
  if (await action('withdraw', 'POST', { publication_id: withdrawal.id, reason: withdrawal.reason.trim() })) withdrawal.id = null
}
</script>

<template>
  <section class="card space-y-3" aria-label="Validation et publication du prix bancaire">
    <div class="flex flex-wrap items-center gap-2"><h3 class="font-semibold">Réponse commerciale bancaire</h3><span class="text-xs text-slate-500">Prix en % du nominal, all-in · {{ formatNumber(received.request.nominal, 0) }} {{ received.request.currency }}</span><button class="btn-ghost btn-sm" :disabled="busy" @click="refresh">Actualiser le contrôle</button></div>
    <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
    <p class="text-xs text-slate-500">Le prix théorique et les marchés restent privés. Seul le récapitulatif commercial validé sera publié au demandeur.</p>
    <div class="flex flex-wrap items-center gap-2 text-xs"><span v-if="received.publication_policy.configured">Politique v{{ received.publication_policy.version }} · {{ received.publication_policy.second_validation_required ? 'Seconde validation obligatoire' : 'Validation par le même utilisateur autorisée' }} · calcul âgé de {{ received.publication_policy.max_calculation_age_minutes }} min au maximum.</span><span v-else>La politique du desk doit être configurée avant préparation.</span><button v-if="auth.canAdministerOrganization" class="btn-ghost btn-sm" :disabled="busy" @click="showPolicy = !showPolicy">Politique du desk</button></div>
    <form v-if="showPolicy && auth.canAdministerOrganization" class="space-y-2 p-3 border rounded-lg" @submit.prevent="savePolicy"><label class="flex items-center gap-2 text-xs"><input v-model="policy.second_validation_required" type="checkbox" />Exiger un second utilisateur pour valider</label><label class="block"><span class="label">Âge maximal du calcul (minutes)</span><input v-model="policy.max_calculation_age_minutes" type="number" min="1" max="10080" class="input" required /></label><label class="block"><span class="label">Motif de configuration</span><input v-model="policy.reason" class="input w-full" minlength="3" maxlength="500" required /></label><button class="btn-secondary btn-sm" :disabled="busy || !policy.max_calculation_age_minutes || policy.reason.trim().length < 3">Enregistrer la politique</button></form>
    <button v-if="canPrepare" class="btn-secondary btn-sm" :disabled="busy || !received.publication_policy.configured || !received.case?.calculations?.length" @click="showEditor = !showEditor">{{ draft ? 'Préparer une nouvelle révision' : 'Préparer le prix commercial' }}</button>
    <form v-if="showEditor && canPrepare" class="space-y-3 border rounded-lg p-3" @submit.prevent="saveDraft">
      <div class="grid sm:grid-cols-2 gap-3"><label><span class="label">Calcul privé utilisé</span><select v-model.number="form.calculation_id" class="select w-full" required><option v-for="run in received.case.calculations" :key="run.id" :value="run.id">#{{ run.id }} · {{ formatDateTime(run.calculated_at) }} · {{ formatNumber(run.price, 4) }} % théorique</option></select></label><label><span class="label">Prix commercial (% du nominal, all-in)</span><input v-model="form.price" inputmode="decimal" class="input w-full" required /></label><label><span class="label">Fermeté</span><select v-model="form.firmness" class="select w-full"><option value="INDICATIVE">Indicative</option><option value="FIRM">Ferme · relation de traitement requise</option></select></label><label><span class="label">Validité jusqu’au · heure locale</span><input v-model="form.valid_until" type="datetime-local" step="1" class="input w-full" required /></label><label><span class="label">Émetteur juridique (obligatoire pour une note)</span><input v-model="form.issuer_name" class="input w-full" maxlength="200" /></label><label><span class="label">Garant juridique (si applicable)</span><input v-model="form.guarantor_name" class="input w-full" maxlength="200" /></label></div>
      <label class="block"><span class="label">Référence documentaire proposée</span><input v-model="form.documentation_reference" class="input w-full" maxlength="1000" /></label>
      <label class="block"><span class="label">Conditions</span><select v-model="form.conditions_type" class="select w-full" @change="form.conditions_type === 'CONDITIONAL' && !form.conditions.length && form.conditions.push({ code: 'OTHER', description: '' })"><option value="NONE">Sans condition supplémentaire</option><option value="CONDITIONAL">Réponse conditionnelle · hors classement conforme</option></select></label>
      <div v-if="form.conditions_type === 'CONDITIONAL'" class="space-y-2"><div v-for="(condition, i) in form.conditions" :key="i" class="flex flex-wrap gap-2"><select v-model="condition.code" class="select"><option value="DOCUMENTATION">Documentation</option><option value="CREDIT_APPROVAL">Accord crédit</option><option value="OTHER">Autre condition</option></select><input v-model="condition.description" class="input flex-1 min-w-0" minlength="3" maxlength="500" required aria-label="Description de la condition" /><button type="button" class="btn-ghost btn-sm" @click="form.conditions.splice(i, 1)">Retirer</button></div><button type="button" class="btn-ghost btn-sm" :disabled="form.conditions.length >= 10" @click="form.conditions.push({ code: 'OTHER', description: '' })">Ajouter une condition</button></div>
      <label class="block"><span class="label">Commentaire partagé</span><textarea v-model="form.comment" class="input w-full" maxlength="1000" rows="2" /></label>
      <p class="text-xs text-slate-500">Enregistrer une modification invalide la validation précédente. Le nominal, la devise et les termes reçus restent figés.</p>
      <button class="btn-primary btn-sm" :disabled="busy || !Number.isFinite(priceValue) || priceValue <= 0 || !form.valid_until || !form.calculation_id">Enregistrer la préparation</button>
    </form>
    <div v-if="draft" class="space-y-2 border rounded-lg p-3"><strong class="text-sm">Récapitulatif commercial · révision {{ draft.revision }}</strong><p class="text-sm">{{ formatNumber(draft.response.price, 4) }} % · {{ draft.response.firmness === 'FIRM' ? 'Ferme' : 'Indicative' }} · valable jusqu’au {{ formatDateTime(draft.response.valid_until) }}</p><p class="text-xs">Contrepartie : {{ draft.response.counterparty_name }} · émetteur : {{ draft.response.issuer_name || 'Sans objet' }} · documentation : {{ draft.response.documentation_reference || 'Sans objet' }}</p><p class="text-xs">{{ draft.response.conditions_type === 'NONE' ? 'Sans condition supplémentaire' : 'Réponse conditionnelle' }}</p><details><summary class="cursor-pointer text-xs">Contenu exact à publier</summary><pre class="payload">{{ JSON.stringify(draft.response, null, 2) }}</pre></details><p class="text-xs">{{ draft.published ? (publications.find(p => p.revision === draft.revision)?.received_at ? 'Publié · réception confirmée par le demandeur' : 'Publié · réception du demandeur en attente') : draft.validation_current ? `Validé le ${formatDateTime(draft.validated_at)} · publication à effectuer` : received.publication_policy.second_validation_required ? 'Seconde validation attendue' : 'Validation attendue' }}</p><div class="flex gap-2 flex-wrap"><button v-if="canValidate" class="btn-secondary btn-sm" :disabled="busy" @click="action('validate', 'POST', decision())">Valider ce récapitulatif</button><button v-if="draft.validation_current && !draft.published && rights.includes('publish_quote') && received.open_for_work && !executionFrozen" class="btn-primary btn-sm" :disabled="busy" @click="action('publish', 'POST', decision())">Publier le prix au demandeur</button></div></div>
    <div v-if="publications.length" class="space-y-2"><h4 class="text-sm font-semibold">Publications conservées</h4>
      <div v-for="reply in publications" :key="reply.id" class="text-xs border rounded-lg p-3 space-y-1">
        <p><strong>{{ reply.response.response_reference }} · v{{ reply.revision }} · {{ formatNumber(reply.response.price, 4) }} %</strong> · {{ publicationStateLabel(reply.state) }}</p>
        <p>Publié {{ formatDateTime(reply.published_at) }} · {{ reply.received_at ? `réception confirmée ${formatDateTime(reply.received_at)}` : 'réception non confirmée' }}</p>
        <RfqTransportStatus :transport="reply.transport" :can-retry="rights.includes('publish_quote')" @updated="refresh" />
        <p v-if="reply.withdrawn_at">Retiré {{ formatDateTime(reply.withdrawn_at) }} · {{ reply.withdrawal_reason }}</p>
        <RfqTransportStatus :transport="reply.withdrawal_transport" :can-retry="rights.includes('publish_quote')" @updated="refresh" />
        <button v-if="!executionFrozen && rights.includes('publish_quote') && ['ACTIVE', 'PENDING_DELIVERY', 'HISTORY'].includes(reply.state)" class="btn-ghost btn-sm" :disabled="busy" @click="withdrawal.id = reply.id; withdrawal.reason = ''">Retirer cette cotation</button>
      </div>
      <form v-if="withdrawal.id" class="space-y-2" @submit.prevent="withdraw"><label class="block"><span class="label">Motif partagé de retrait (avant acceptation reçue)</span><textarea v-model="withdrawal.reason" class="input w-full" minlength="3" maxlength="500" required /></label><button class="btn-secondary btn-sm" :disabled="busy || withdrawal.reason.trim().length < 3">Confirmer le retrait</button><button type="button" class="btn-ghost btn-sm" @click="withdrawal.id = null">Annuler</button></form>
    </div>
  </section>
</template>

<style scoped>
.payload { white-space: pre-wrap; overflow-wrap: anywhere; font-size: .7rem; padding: .75rem; background: var(--surface2); border-radius: var(--radius-sm); }
</style>
