<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { apiFetch } from '../utils/api.js'
import { useRfqStore } from '../stores/rfq.js'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'
import SensitiveValue from './SensitiveValue.vue'
import RfqElectronicExecutionPanel from './RfqElectronicExecutionPanel.vue'
import { formatInt, formatPercent, formatDateTime } from '../utils/format.js'

const props = defineProps({ rfq: { type: Object, required: true } })
const store = useRfqStore()
const opened = ref(false)
const busy = ref(false)
const error = ref('')
const terms = ref(null)
const commandKey = ref('')
const selected = computed(() => props.rfq.quotes?.find(q => q.id === props.rfq.selected_quote_id))
const active = computed(() => props.rfq.execution_agreements?.find(item => item.state !== 'CANCELLED'))
const allowed = computed(() => !props.rfq.pilot_desk_id || props.rfq.access_rights?.includes('book'))
const request = reactive({ source: 'PHONE', reference: '', bank_contact: '' })
const confirmation = reactive({ execution_reference: '', acceptance_received_at: '', confirmed_at: '',
  acceptance_evidence: '', source: 'BANK_CONFIRMATION', evidence: '', bank_contact: '' })
const cancelReason = ref('')
let contextRevision=0
const labels = { REQUESTED: 'Traitement demandé · confirmation attendue', CONFIRMED: 'Traitement confirmé',
  BOOKED_LOCALLY: 'Booké localement', CANCELLED: 'Demande annulée' }
const confirmationComplete = computed(() => confirmation.execution_reference.trim().length >= 3
  && confirmation.bank_contact.trim().length >= 3 && confirmation.acceptance_received_at && confirmation.confirmed_at
  && confirmation.acceptance_evidence.trim().length >= 3 && confirmation.evidence.trim().length >= 3)

watch([()=>props.rfq.id,()=>props.rfq.selected_quote_id,()=>active.value?.id],()=>{
  contextRevision++
  opened.value=false;error.value='';terms.value=null;busy.value=false;commandKey.value='';cancelReason.value=''
  Object.assign(request,{source:'PHONE',reference:'',bank_contact:''})
  Object.assign(confirmation,{execution_reference:'',acceptance_received_at:'',confirmed_at:'',
    acceptance_evidence:'',source:'BANK_CONFIRMATION',evidence:'',bank_contact:''})
},{flush:'sync'})
watch(opened,value=>{if(!value){contextRevision++;busy.value=false}},{flush:'sync'})

async function open() {
  const id = props.rfq.id
  error.value = ''; opened.value = true
  const revision=++contextRevision
  request.bank_contact = selected.value?.contact || ''
  confirmation.bank_contact = active.value?.bank_contact || request.bank_contact
  if (active.value) return
  busy.value = true
  try {
    const res = await apiFetch(`/api/rfq/${id}/terms`)
    if (!res.ok) throw new Error('Les termes Product n’ont pas pu être chargés.')
    const value = await res.json()
    if (contextRevision===revision && props.rfq.id === id) { terms.value = value; commandKey.value = crypto.randomUUID() }
  } catch (e) { if (contextRevision===revision) error.value = e.message }
  finally { if (contextRevision===revision) busy.value = false }
}

async function run(action) {
  if (busy.value) return
  const id = props.rfq.id
  const revision=contextRevision
  busy.value = true; error.value = ''
  try { await action(); if (contextRevision===revision && props.rfq.id === id) opened.value = false }
  catch (e) { if (contextRevision===revision) error.value = e.message }
  finally { if (contextRevision===revision) busy.value = false }
}
function declare() {
  const id = props.rfq.id
  return run(() => store.declareTreatment(id, { ...request, quote_id: selected.value.id,
    expected_terms_version: terms.value.terms_version, expected_terms_fingerprint: terms.value.terms_fingerprint,
    command_key: commandKey.value }))
}
function confirm() {
  if(!active.value || !confirmationComplete.value) {error.value='Renseignez les preuves de confirmation de ce dossier.';return}
  const id = props.rfq.id, agreement = active.value
  return run(() => store.confirmTreatment(id, agreement.id, { ...confirmation,
    expected_snapshot_hash: agreement.snapshot_hash,
    acceptance_received_at: new Date(confirmation.acceptance_received_at).toISOString(),
    confirmed_at: new Date(confirmation.confirmed_at).toISOString() }))
}
</script>

<template>
  <RfqElectronicExecutionPanel :rfq="rfq" />
  <section v-if="!rfq.electronic_execution && (selected || rfq.execution_agreements?.length)" class="card space-y-2">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <h3 class="font-semibold text-sm">Accord de traitement</h3>
        <p class="text-xs">{{ active ? labels[active.state] : 'Réponse retenue · accord à consigner' }}</p>
      </div>
      <button v-if="allowed && !rfq.booked_deal && (active || rfq.kind === 'to_trade')" class="btn-secondary btn-sm" @click="open">
        {{ active?.state === 'REQUESTED' ? 'Consigner la confirmation' : active ? 'Voir l’accord' : 'Consigner le traitement' }}
      </button>
    </div>
    <p v-if="!active && selected?.origin === 'NETWORK'" class="text-xs">La sélection reste locale. Une confirmation de traitement est requise avant booking.</p>
    <p v-else-if="!active" class="text-xs">La saisie manuelle reste disponible ; vous pouvez conserver ici la preuve de l’accord.</p>
    <template v-if="active">
      <p class="text-xs"><span class="font-mono">{{ active.execution_reference || 'Référence d’exécution à recevoir' }}</span> · {{ active.bank_contact }}</p>
      <p v-if="active.confirmed_at" class="text-xs">{{ active.confirmation_source === 'PHONE_DECLARATION' ? 'Accord téléphonique déclaré' : 'Confirmation reçue de la banque' }} · {{ formatDateTime(active.confirmed_at) }}</p>
      <p v-if="active.written_confirmation_pending" class="text-xs">Confirmation écrite à suivre.</p>
      <AlertMessage v-if="active.review_required_reason" kind="warning">{{ active.review_required_reason }} L’accord confirmé reste conservé.</AlertMessage>
      <AlertMessage v-if="active.booking_block_reason && !rfq.booked_deal" kind="warning">Accord conservé · inscription locale bloquée : {{ active.booking_block_reason }}</AlertMessage>
    </template>
    <details v-if="rfq.execution_agreements?.length" class="text-xs">
      <summary class="cursor-pointer">Historique des traitements</summary>
      <p v-for="item in rfq.execution_agreements" :key="item.id" class="mt-2">{{ labels[item.state] }} · {{ formatDateTime(item.requested_at) }}<span v-if="item.cancellation_reason"> · {{ item.cancellation_reason }}</span></p>
    </details>
  </section>

  <BaseModal v-model="opened" title="Accord de traitement avant booking" max-width="800px">
    <div class="space-y-4">
      <p class="text-xs">{{ rfq.reference }} · {{ selected?.provider }} · {{ active ? labels[active.state] : 'Déclaration d’une demande externe' }}</p>
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <p v-if="busy" class="text-xs">Enregistrement ou chargement…</p>
      <div class="card text-sm space-y-1">
        <p><SensitiveValue>{{ formatPercent(active?.snapshot.price ?? selected?.price) }}</SensitiveValue> · <SensitiveValue>{{ formatInt(active?.snapshot.nominal ?? rfq.params?.notional) }} {{ active?.snapshot.currency ?? rfq.params?.currency }}</SensitiveValue></p>
        <p class="text-xs">Prix all-in en % du nominal, totalité du nominal demandé.</p>
        <p class="text-xs break-all">Product · termes v{{ active?.snapshot.terms_version ?? terms?.terms_version }} · {{ active?.snapshot.terms_fingerprint ?? terms?.terms_fingerprint }}</p>
      </div>
      <template v-if="!active">
        <AlertMessage kind="info">Déclarez une demande réellement faite à la banque par téléphone, courriel ou document. Cette action conserve sa preuve dans Structura.</AlertMessage>
        <div class="grid sm:grid-cols-2 gap-3">
          <label><span class="label">Canal de la demande</span><select v-model="request.source" class="select w-full"><option value="PHONE">Téléphone</option><option value="EMAIL">Courriel</option><option value="DOCUMENT">Document</option></select></label>
          <label><span class="label">Interlocuteur bancaire</span><input v-model="request.bank_contact" class="input w-full" /></label>
          <label class="sm:col-span-2"><span class="label">Référence / preuve de la demande externe</span><input v-model="request.reference" class="input w-full" /></label>
        </div>
      </template>
      <template v-else-if="active.state === 'REQUESTED'">
        <p class="text-xs">Demande déclarée le {{ formatDateTime(active.requested_at) }} pendant la validité du prix. La réception d’acceptation doit être postérieure à l’émission de la réponse et antérieure à son expiration. Les preuves sont obligatoires.</p>
        <div class="grid sm:grid-cols-2 gap-3">
          <label><span class="label">Référence d’exécution commune / externe</span><input v-model="confirmation.execution_reference" class="input w-full" /></label>
          <label><span class="label">Interlocuteur bancaire</span><input v-model="confirmation.bank_contact" class="input w-full" /></label>
          <label><span class="label">Réception de l’acceptation par la banque · heure locale</span><input v-model="confirmation.acceptance_received_at" type="datetime-local" step="1" class="input w-full" /></label>
          <label><span class="label">Heure de l’accord confirmé · heure locale</span><input v-model="confirmation.confirmed_at" type="datetime-local" step="1" class="input w-full" /></label>
          <label class="sm:col-span-2"><span class="label">Preuve du canal et de la réception de l’acceptation</span><input v-model="confirmation.acceptance_evidence" class="input w-full" /></label>
          <label class="sm:col-span-2"><span class="label">Mode de confirmation</span><select v-model="confirmation.source" class="select w-full"><option value="BANK_CONFIRMATION">Confirmation reçue de la banque · courriel/document</option><option value="PHONE_DECLARATION">Accord téléphonique déclaré · écrit à suivre</option></select></label>
          <label class="sm:col-span-2"><span class="label">Preuve de l’accord exact · référence courriel/document ou compte rendu</span><textarea v-model="confirmation.evidence" rows="3" class="input w-full" /></label>
        </div>
        <details class="text-xs"><summary class="cursor-pointer">Annuler une demande non confirmée</summary><label class="block mt-2"><span class="label">Motif</span><input v-model="cancelReason" class="input w-full" /></label><button class="btn-secondary btn-sm mt-2" :disabled="busy || cancelReason.trim().length < 3" @click="run(() => store.cancelTreatment(rfq.id, active.id, cancelReason))">Consigner l’annulation</button></details>
      </template>
      <template v-else>
        <p class="text-xs">{{ active.confirmation_source === 'PHONE_DECLARATION' ? 'Accord téléphonique déclaré' : 'Confirmation reçue de la banque' }} · {{ active.execution_reference }}</p>
        <dl class="grid sm:grid-cols-2 gap-3 text-xs"><div><dt>Acceptation reçue</dt><dd>{{ formatDateTime(active.acceptance_received_at) }}</dd></div><div><dt>Accord confirmé</dt><dd>{{ formatDateTime(active.confirmed_at) }}</dd></div></dl>
        <p class="text-xs whitespace-pre-wrap break-words">Réception : {{ active.acceptance_evidence }}</p><p class="text-xs whitespace-pre-wrap break-words">Confirmation : {{ active.confirmation_evidence }}</p>
      </template>
    </div>
    <template #footer>
      <button class="btn-secondary" :disabled="busy" @click="opened = false">Revenir à la RFQ</button>
      <button v-if="!active" class="btn-primary" :disabled="busy || !terms || request.reference.trim().length < 3 || request.bank_contact.trim().length < 3" @click="declare">Déclarer le traitement demandé</button>
      <button v-else-if="active.state === 'REQUESTED'" class="btn-primary" :disabled="busy || !confirmationComplete" @click="confirm">Consigner l’accord confirmé</button>
    </template>
  </BaseModal>
</template>
