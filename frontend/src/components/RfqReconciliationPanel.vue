<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { apiFetch, apiErrorMessage } from '../utils/api.js'
import { durableCommand } from '../utils/commands.js'
import { formatDateTime, formatInt, formatPercent } from '../utils/format.js'
import AlertMessage from './ui/AlertMessage.vue'
import SensitiveValue from './SensitiveValue.vue'
import RfqTransportStatus from './RfqTransportStatus.vue'
import { reconciliationLabels as labels } from '../utils/rfqReconciliationLabels.js'

const props = defineProps({ entry: Object, canResume: Boolean, contextRevision: Number })
const state = ref(null), busy = ref(false), error = ref('')
let generation = 0, mounted = true, timer
const fields = { price: 'Prix (%)', nominal: 'Nominal', currency: 'Devise', side: 'Sens',
  terms_fingerprint: 'Empreinte contractuelle', documentation_reference: 'Documentation',
  trade_date: 'Date de trade', transaction_format: 'Format', instrument_family: 'Instrument', payoff_family: 'Famille de payoff',
  legal_mapping_matches: 'Mapping juridique local', strike_date: 'Date de strike', value_date: 'Date de valeur',
  maturity_date: 'Maturité', payment_date: 'Paiement', decision_hash: 'Empreinte de décision',
  execution_state: 'Décision', booking_without_confirmation: 'Booking sans confirmation', booking_regression: 'Booking précédemment déclaré puis absent' }
function display(field, value) {
  if (field === 'price') return formatPercent(value)
  if (field === 'nominal') return formatInt(value)
  if (typeof value === 'boolean') return value ? 'Oui' : 'Non'
  return ({ BUY: 'Achat', SELL: 'Vente', CONFIRMED: 'Confirmée', REJECTED: 'Refusée', BOOKED: 'Booké', MISSING: 'Absent' })[value] || value
}
watch([() => props.entry?.id, () => props.contextRevision], () => {
  generation++; state.value = props.entry?.reconciliation || null; busy.value = false; error.value = ''
}, { immediate: true, flush: 'sync' })
watch(() => props.entry?.reconciliation, value => { if (value && !busy.value) state.value = value })
const current = (id, ticket) => mounted && props.entry?.id === id && generation === ticket
async function read(response) {
  const data = await response.json()
  if (!response.ok) throw new Error(apiErrorMessage(data))
  return data
}
async function refresh(resume = false) {
  if (busy.value || !props.entry?.id || (resume && !props.canResume)) return
  const id = props.entry.id, ticket = generation
  busy.value = true; error.value = ''
  try {
    const url = `/api/rfq-reconciliation/${id}`
    const data = resume ? await durableCommand('rfq-reconcile', { execution_id: id }, async key =>
      read(await apiFetch(url + '/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command_key: key }) }))) : await read(await apiFetch(url))
    if (current(id, ticket)) state.value = data
  } catch (failure) { if (current(id, ticket)) error.value = failure.message }
  finally { if (current(id, ticket)) busy.value = false }
}
onMounted(() => { timer = setInterval(() => { if (!document.hidden) refresh() }, 5000) })
onUnmounted(() => { mounted = false; generation++; clearInterval(timer) })
</script>

<template>
  <section v-if="entry" aria-label="Rapprochement des deux livres" class="border-t pt-3 space-y-2 text-xs">
    <h4 class="font-semibold">Rapprochement des deux livres</h4>
    <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
    <p :class="state?.state === 'MISMATCH' ? 'text-red-600' : ''">{{ labels[state?.state] || 'État à actualiser' }}</p>
    <p>Derniers états déclarés · chaque installation conserve son livre et ses contrôles.</p>
    <p v-if="state?.peer">État distant v{{ state.peer_version }} observé le {{ formatDateTime(state.peer.observed_at) }}, reçu le {{ formatDateTime(state.peer_received_at) }}.</p>
    <p v-else>Aucun état distant reçu : aucune concordance ne peut être conclue.</p>
    <p v-if="state?.local_changed_since_publication">Le livre local a changé depuis notre dernière publication : relancez le rapprochement.</p>
    <div v-if="state?.differences?.length" class="overflow-x-auto">
      <table class="w-full"><thead><tr><th>Livre</th><th>Champ</th><th>Attendu</th><th>Constaté</th></tr></thead>
        <tbody><tr v-for="(diff, index) in state.differences" :key="index"><td>{{ diff.side === 'LOCAL' ? 'Local' : 'Distant' }}</td><td>{{ fields[diff.field] || diff.field }}</td><td class="break-all"><SensitiveValue>{{ display(diff.field, diff.expected) }}</SensitiveValue></td><td class="break-all"><SensitiveValue>{{ display(diff.field, diff.actual) }}</SensitiveValue></td></tr></tbody>
      </table>
    </div>
    <p v-if="['LOCAL_BOOKING_MISSING', 'BOTH_BOOKINGS_MISSING'].includes(state?.state)">Reprenez le booking local depuis le dossier confirmé. La relance des échanges ne crée aucun Deal.</p>
    <div class="flex flex-wrap gap-2"><button class="btn-secondary btn-sm" :disabled="busy" @click="refresh()">Actualiser le rapprochement</button><button v-if="canResume" class="btn-secondary btn-sm" :disabled="busy" @click="refresh(true)">Rapprocher et reprendre les échanges</button></div>
    <RfqTransportStatus v-if="state?.transport" :transport="state.transport" :can-retry="false" />
  </section>
</template>
