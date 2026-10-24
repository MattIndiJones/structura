<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiFetch, apiErrorMessage } from '../utils/api.js'
import { useRfqStore } from '../stores/rfq.js'
import { formatDateTime, formatInt, formatPercent } from '../utils/format.js'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'
import SensitiveValue from './SensitiveValue.vue'
import RfqTransportStatus from './RfqTransportStatus.vue'
import RfqReconciliationPanel from './RfqReconciliationPanel.vue'

const props = defineProps({ rfq: Object, received: Object, contextRevision: { type: Number, default: 0 } })
const emit = defineEmits(['updated'])
const store = useRfqStore()
const bankSide = computed(() => !!props.received)
const dossier = computed(() => props.received || props.rfq)
const entry = computed(() => dossier.value?.electronic_execution)
const selected = computed(() => props.rfq?.quotes?.find(q => q.id === props.rfq.selected_quote_id))
const permitted = computed(() => bankSide.value ? props.received.rights?.includes('book')
  : !props.rfq?.pilot_desk_id || props.rfq.access_rights?.includes('book'))
const quote = computed(() => entry.value?.quote || selected.value)
const opened = ref(false), busy = ref(false), error = ref(''), reason = ref(''), reviewed = ref(false), terms = ref(null)
let generation = 0, mounted = true, timer
const labels = { PENDING: 'Demande enregistrée · confirmation bancaire attendue',
  RECEIVED: 'Acceptation reçue · décision bancaire attendue', CONFIRMED: 'Exécution confirmée électroniquement',
  REJECTED: 'Exécution refusée par la banque' }
const current = (id, ticket) => mounted && dossier.value?.id === id && generation === ticket
watch([() => dossier.value?.id, () => props.contextRevision, () => props.rfq?.selected_quote_id], () => {
  generation++; opened.value = false; busy.value = false; error.value = ''; reason.value = ''; reviewed.value = false; terms.value = null
}, { flush: 'sync' })
watch(opened, value => { if (!value) { generation++; busy.value = false } }, { flush: 'sync' })
onMounted(() => { timer = setInterval(() => {
  if (!bankSide.value && entry.value?.state === 'PENDING' && !busy.value && !opened.value && !document.hidden) refresh()
}, 5000) })
onUnmounted(() => { mounted = false; generation++; clearInterval(timer) })

async function json(response) {
  const data = await response.json()
  if (!response.ok) throw new Error(apiErrorMessage(data))
  return data
}
async function refresh() {
  if (busy.value) return
  const id = dossier.value.id, ticket = generation, context = props.contextRevision
  busy.value = true; error.value = ''
  try {
    if (bankSide.value) {
      const data = await json(await apiFetch(`/api/rfq-inbox/${id}`))
      if (current(id, ticket)) emit('updated', data, context)
    } else await store.fetchOne(id)
  } catch (failure) { if (current(id, ticket)) error.value = failure.message }
  finally { if (current(id, ticket)) busy.value = false }
}
async function open() {
  const id = dossier.value.id, ticket = ++generation
  error.value = ''; reviewed.value = false; reason.value = ''; terms.value = null; opened.value = true
  if (bankSide.value || entry.value) return
  busy.value = true
  try {
    const data = await json(await apiFetch(`/api/rfq/${id}/terms`))
    if (current(id, ticket) && opened.value) terms.value = data
  } catch (failure) { if (current(id, ticket)) error.value = failure.message }
  finally { if (current(id, ticket)) busy.value = false }
}
async function send(decision) {
  if (busy.value || !permitted.value || !reviewed.value || (!bankSide.value && !terms.value)
      || (bankSide.value && reason.value.trim().length < 3)) return
  const id = dossier.value.id, ticket = generation, context = props.contextRevision
  busy.value = true; error.value = ''
  try {
    if (bankSide.value) {
      const data = await json(await apiFetch(`/api/rfq-inbox/${id}/electronic-execution/${entry.value.id}/decision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_request_hash: entry.value.request_hash, decision, reason: reason.value.trim() }),
      }))
      if (current(id, ticket)) emit('updated', data, context)
    } else await store.requestElectronicExecution(id, { quote_id: selected.value.id,
      expected_terms_version: terms.value.terms_version, expected_terms_fingerprint: terms.value.terms_fingerprint })
    if (current(id, ticket)) opened.value = false
  } catch (failure) { if (current(id, ticket)) error.value = failure.message }
  finally { if (current(id, ticket)) busy.value = false }
}
</script>

<template>
  <section v-if="entry || selected?.origin === 'NETWORK'" class="card space-y-3" aria-label="Confirmation électronique d’exécution">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div class="min-w-0"><h3 class="font-semibold text-sm">Confirmation électronique d’exécution</h3>
        <p class="text-xs">{{ entry ? labels[entry.state] : 'Réponse réseau retenue · demande à envoyer' }}</p></div>
      <button v-if="entry" class="btn-secondary btn-sm" :disabled="busy" @click="refresh">Actualiser l’exécution</button>
    </div>
    <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
    <p v-if="entry" class="text-xs font-mono break-all">{{ entry.execution_reference }}</p>
    <p class="text-xs">La livraison d’un message ne vaut pas accord. La décision bancaire confirme la cotation exacte ; chaque booking conserve ses contrôles locaux.</p>
    <p v-if="entry?.received_at" class="text-xs">Acceptation reçue par la banque le {{ formatDateTime(entry.received_at) }}.</p>
    <p v-if="entry?.decision" class="text-xs">{{ entry.decision.reason }} · {{ formatDateTime(entry.decision.decided_at) }}</p>
    <template v-if="entry?.transport"><p class="text-xs font-semibold">{{ bankSide ? 'Acheminement de la décision' : 'Acheminement de la demande' }}</p>
      <RfqTransportStatus :transport="entry.transport" :can-retry="!!permitted" @updated="refresh" /></template>
    <p v-if="entry?.state === 'PENDING'" class="text-xs">Aucun booking autorisé avant réception de la confirmation bancaire. Une reprise conserve la même intention.</p>
    <p v-if="entry?.state === 'REJECTED'" class="text-xs">Le refus est conservé. Une nouvelle négociation exige un nouveau tour.</p>
    <p v-if="entry?.booked_deal" class="text-xs">Booké localement · {{ entry.booked_deal.reference }}</p>
    <button v-if="permitted && ((!entry && !rfq?.execution_agreements?.some(a => a.state !== 'CANCELLED') && rfq?.kind === 'to_trade') || (bankSide && entry?.state === 'RECEIVED'))"
      class="btn-primary btn-sm" @click="open">{{ bankSide ? 'Examiner la demande d’exécution' : 'Demander la confirmation électronique' }}</button>
    <p v-if="bankSide && entry?.state === 'RECEIVED' && !permitted" class="text-xs">La décision nécessite le droit de booking sur ce desk.</p>
    <RfqReconciliationPanel v-if="entry" :entry="entry" :can-resume="!!permitted" :context-revision="contextRevision" />
  </section>
  <BaseModal v-model="opened" :title="bankSide ? 'Décision bancaire d’exécution' : 'Demande de confirmation électronique'" max-width="760px">
    <div class="space-y-3 text-sm">
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <p>Prix <SensitiveValue>{{ formatPercent(quote?.price) }}</SensitiveValue> · nominal <SensitiveValue>{{ formatInt(entry?.quote.nominal ?? rfq?.params?.notional) }} {{ entry?.quote.currency ?? rfq?.params?.currency }}</SensitiveValue>.</p>
      <p>Réponse {{ entry?.quote.response_reference || selected?.provider }} · révision {{ entry?.quote.revision ?? selected?.revision }}.</p>
      <p v-if="entry">{{ entry.quote.requester }} {{ entry.quote.side === 'BUY' ? 'achète à' : 'vend à' }} {{ entry.quote.organization }} · termes partagés v{{ entry.quote.terms_version }}.</p>
      <p v-if="entry?.quote.issuer_name">Émetteur : {{ entry.quote.issuer_name }} · {{ entry.quote.documentation_reference }}.</p>
      <p v-if="entry" class="font-mono text-xs break-all">{{ entry.execution_reference }}</p>
      <p v-else>La banque contrôlera la validité du prix à sa réception, puis confirmera ou refusera explicitement. Cet envoi ne booke aucun Deal.</p>
      <label class="flex gap-2 items-start text-xs"><input v-model="reviewed" type="checkbox" />J’ai vérifié le prix, le nominal et la révision de cotation affichés.</label>
      <label v-if="bankSide" class="block"><span class="label">Motif de la décision bancaire</span><textarea v-model="reason" class="input w-full" maxlength="500" rows="3" /></label>
    </div>
    <template #footer><button class="btn-secondary" :disabled="busy" @click="opened = false">Revenir au dossier</button>
      <template v-if="bankSide"><button class="btn-secondary" :disabled="busy || !reviewed || reason.trim().length < 3" @click="send('REJECTED')">Refuser l’exécution</button><button class="btn-primary" :disabled="busy || !reviewed || reason.trim().length < 3" @click="send('CONFIRMED')">Confirmer l’exécution</button></template>
      <button v-else class="btn-primary" :disabled="busy || !reviewed || !terms" @click="send()">Envoyer la demande électronique</button>
    </template>
  </BaseModal>
</template>
