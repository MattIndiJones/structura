<script setup>
import { computed, onMounted, ref, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import { useAuthStore } from '../stores/auth.js'
import BaseModal from '../components/ui/BaseModal.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import BackLink from '../components/ui/BackLink.vue'
import { formatDate, formatDateTime, formatNumber } from '../utils/format.js'
import RfqBankQuotePanel from '../components/RfqBankQuotePanel.vue'
import RfqElectronicExecutionPanel from '../components/RfqElectronicExecutionPanel.vue'
import { reconciliationLabels } from '../utils/rfqReconciliationLabels.js'

const rows = ref([])
const selected = ref(null)
const show = ref(false)
const busy = ref(false)
const error = ref('')
const more = ref(false)
const router = useRouter()
const route = useRoute()
const assignees = ref([])
const assignedTo = ref(null)
const assignmentReason = ref('')
const assigning = ref(false)
const showAssignment = ref(false)
const isResponsible = computed(() => selected.value?.case?.responsible_user_id === auth.user?.id)
const auth = useAuthStore()
let opening = 0
watch(show,value=>{if(!value){opening++;busy.value=false;assigning.value=false;showAssignment.value=false}},{flush:'sync'})
onUnmounted(()=>{opening++})
const isCurrent=(ticket,id)=>ticket===opening && show.value && selected.value?.id===id
async function json(response) {
  const value = await response.json()
  if (!response.ok) throw new Error(value.detail?.message || value.detail || 'La réception des RFQ est indisponible.')
  return value
}
async function load(append = false) {
  busy.value = true
  error.value = ''
  try {
    const before = append ? `?before_id=${rows.value.at(-1).id}` : ''
    const data = await json(await apiFetch(`/api/rfq-inbox${before}`))
    rows.value = append ? [...rows.value, ...data] : data
    more.value = data.length === 100
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
async function open(item) {
  show.value=false;selected.value=null;showAssignment.value=false;assigning.value=false
  const ticket = ++opening
  busy.value = true
  error.value = ''
  try {
    const data = await json(await apiFetch(`/api/rfq-inbox/${item.id}`))
    if (ticket !== opening) return
    selected.value = data
    showAssignment.value = false
    show.value = true
    // Acknowledge only after the user has explicitly opened this request.
    const acknowledged = await json(await apiFetch(`/api/rfq-inbox/${item.id}/read`, { method: 'POST' }))
    if (ticket !== opening) return
    selected.value = acknowledged
    rows.value = rows.value.map(row => row.id === item.id ? { ...row, ...acknowledged } : row)
  } catch (failure) { if(ticket===opening) error.value = failure.message }
  finally { if (ticket === opening) busy.value = false }
}
function apply(data,ticket,id) {
  if(!isCurrent(ticket,id)) return
  selected.value = data
  rows.value = rows.value.map(row => row.id === data.id ? { ...row, ...data } : row)
}
function applyQuoteUpdate(data,ticket) {
  apply(data,ticket,data.id)
}
async function claim() {
  const id=selected.value.id,ticket=opening
  busy.value = true
  error.value = ''
  try { apply(await json(await apiFetch(`/api/rfq-inbox/${id}/claim`, { method: 'POST' })),ticket,id) }
  catch (failure) { if(isCurrent(ticket,id)) error.value = failure.message }
  finally { if(isCurrent(ticket,id)) busy.value = false }
}
async function prepareAssignment() {
  const id=selected.value.id,ticket=opening
  error.value = ''
  try {
    const members=await json(await apiFetch(`/api/rfq-inbox/${id}/members`))
    if(!isCurrent(ticket,id)) return
    assignees.value = members
    assignedTo.value = selected.value.case.responsible_user_id
    assignmentReason.value = ''
    showAssignment.value = true
  } catch (failure) { if(isCurrent(ticket,id)) error.value = failure.message }
}
async function assign() {
  if(assigning.value || !selected.value) return
  const id=selected.value.id,ticket=opening
  assigning.value = true
  error.value = ''
  try {
    apply(await json(await apiFetch(`/api/rfq-inbox/${id}/assignment`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ responsible_user_id: assignedTo.value, expected_revision: selected.value.case.revision,
        reason: assignmentReason.value.trim() }),
    })),ticket,id)
    if(isCurrent(ticket,id)) showAssignment.value = false
  } catch (failure) { if(isCurrent(ticket,id)) error.value = failure.message }
  finally { if(isCurrent(ticket,id)) assigning.value = false }
}
function openPricer() {
  router.push({ path: `/products/${selected.value.case.product_id}/pricer`, query: { receivedRfq: selected.value.id } })
}
onMounted(async () => {
  await load()
  const requested = Number(route.query.open)
  if (requested > 0) await open({ id: requested })
})
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
    <div class="page-header px-4 sm:px-6 pt-4 pb-3 mb-0 shrink-0 flex-wrap gap-2">
      <div class="flex items-center gap-3"><BackLink :fallback="{ path: '/', query: { category: 'competitive_bidding' } }" /><h1 class="page-title">RFQ reçues</h1></div>
      <button class="btn-secondary btn-sm" :disabled="busy" @click="load()">Actualiser</button>
    </div>
    <div class="flex-1 min-h-0 overflow-auto px-4 sm:px-6 pb-4 space-y-3">
      <p class="text-xs text-slate-500">File de vos desks habilités. Prenez en charge une demande puis ouvrez le Product reçu dans votre Pricer. Les hypothèses et prix restent privés à la banque.</p>
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <p v-if="!rows.length" class="text-sm text-slate-500">{{ busy ? 'Chargement…' : 'Aucune demande reçue pour vos desks.' }}</p>
      <div v-else class="table-shell overflow-x-auto"><table><thead><tr><th>Échange</th><th>Demandeur</th><th>Produit</th><th>Nominal</th><th>Délai</th><th>Responsable</th><th>Travail bancaire</th><th></th></tr></thead><tbody>
        <tr v-for="item in rows" :key="item.id"><td>{{ item.exchange_reference }}<div class="text-xs">Tour {{ item.round_number }} · {{ item.recipient.desk }}</div></td><td>{{ item.requester.organization }}</td><td>{{ item.title }}</td><td>{{ formatNumber(item.nominal, 0) }} {{ item.currency }}</td><td>{{ formatDateTime(item.response_deadline) }}</td><td>{{ item.case?.responsible_name || 'À prendre en charge' }}</td><td>{{ reconciliationLabels[item.reconciliation_state] || (!item.open_for_work ? 'Tour fermé ou délai dépassé' : item.case?.calculations?.length ? 'Calcul privé conservé' : item.case ? 'En cours' : 'Reçue') }}</td><td><button class="btn-secondary btn-sm" @click="open(item)">Ouvrir</button></td></tr>
      </tbody></table></div>
      <button v-if="more" class="btn-secondary btn-sm" :disabled="busy" @click="load(true)">Charger les demandes précédentes</button>
    </div>
    <BaseModal v-model="show" title="Demande reçue · termes figés" max-width="1100px">
      <div v-if="selected" class="space-y-4 text-sm">
        <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
        <AlertMessage v-if="!selected.open_for_work" kind="warning">{{ selected.block_reason }}. Les termes et calculs historiques restent consultables.</AlertMessage>
        <div class="card flex flex-wrap gap-3 items-center">
          <span class="text-xs">{{ selected.case ? `Responsable : ${selected.case.responsible_name}` : 'À prendre en charge par le desk' }}</span>
          <button v-if="!selected.case && selected.rights.includes('prepare')" class="btn-primary btn-sm" :disabled="busy || !selected.open_for_work" @click="claim">Prendre en charge</button>
          <button v-if="selected.case && (selected.open_for_work || selected.electronic_execution?.state === 'CONFIRMED' && !selected.electronic_execution?.booked_deal) && (isResponsible || selected.rights.includes('organize')) && selected.rights.includes('prepare')" class="btn-secondary btn-sm" :disabled="busy" @click="prepareAssignment">Réaffecter</button>
          <button v-if="selected.case?.product_id && isResponsible && selected.rights.includes('price')" class="btn-primary btn-sm" :disabled="busy || (!selected.open_for_work && !selected.booking_recovery_available)" @click="openPricer">{{ !selected.open_for_work && selected.booking_recovery_available ? 'Reprendre le booking confirmé' : 'Ouvrir dans le Pricer bancaire' }}</button>
        </div>
        <section v-if="selected.case?.calculations?.length" class="card space-y-2"><h3 class="font-semibold">Calculs privés conservés</h3><p class="text-xs text-slate-500">Prix théoriques en % du nominal. Ces calculs ne sont pas publiés au demandeur.</p><div class="table-shell overflow-x-auto"><table><thead><tr><th>Calcul</th><th>Date</th><th>Valorisation</th><th>Prix théorique</th></tr></thead><tbody><tr v-for="run in selected.case.calculations" :key="run.id"><td>#{{ run.id }}</td><td>{{ formatDateTime(run.calculated_at) }}</td><td>{{ formatDate(run.valuation_date) || 'À l’émission' }}</td><td>{{ formatNumber(run.price, 4) }} %</td></tr></tbody></table></div></section>
        <RfqElectronicExecutionPanel v-if="selected.electronic_execution" :received="selected" :context-revision="opening" @updated="applyQuoteUpdate" />
        <RfqBankQuotePanel v-if="selected.case" :received="selected" :context-revision="opening" @updated="applyQuoteUpdate" />
        <p class="font-semibold">{{ selected.request.title }} · {{ selected.exchange_reference }} · tour {{ selected.round_number }}</p>
        <p>{{ selected.request.requester.organization }} · {{ selected.request.requester.desk }} · {{ selected.request.side === 'BUY' ? 'Achat du demandeur' : 'Vente du demandeur' }} · {{ formatNumber(selected.request.nominal, 0) }} {{ selected.request.currency }}</p>
        <p class="text-xs">Prix en % du nominal, all-in · délai {{ formatDateTime(selected.request.response_deadline) }} · livré {{ formatDateTime(selected.delivered_at) }}</p>
        <p class="text-xs">Contact : {{ selected.request.requester.contact.name }} · {{ selected.request.requester.contact.email }}</p>
        <p class="text-xs">{{ selected.request.product_reference }} · termes v{{ selected.request.terms_version }} · <span class="font-mono break-all">{{ selected.request.terms_fingerprint }}</span></p>
        <dl class="grid grid-cols-2 gap-2 text-xs"><dt>Strike</dt><dd>{{ formatDate(selected.request.terms.strike_date) || '—' }}</dd><dt>Valeur</dt><dd>{{ formatDate(selected.request.terms.value_date) || '—' }}</dd><dt>Maturité</dt><dd>{{ formatDate(selected.request.terms.maturity_date) || '—' }}</dd><dt>Paiement</dt><dd>{{ formatDate(selected.request.terms.payment_date) || '—' }}</dd></dl>
        <div class="table-shell overflow-x-auto"><table><thead><tr><th>Paramètre</th><th>Valeur</th></tr></thead><tbody><tr v-for="parameter in selected.request.terms.parameters" :key="parameter.name"><td>{{ parameter.name }}</td><td>{{ JSON.stringify(parameter.value) }}{{ parameter.is_pct ? ' (fraction de pourcentage)' : '' }}</td></tr></tbody></table></div>
        <p class="text-xs">Panier : {{ selected.request.terms.underlyings.map(item => `${item.name} (${item.ticker}, ${item.ccy})`).join(' · ') }}</p>
        <details><summary class="cursor-pointer text-xs">Script et calendrier contractuels</summary><pre class="payload">{{ selected.request.terms.script }}</pre><pre class="payload">{{ JSON.stringify(selected.request.terms.resolved_events || selected.request.terms.schedule, null, 2) }}</pre></details>
        <details><summary class="cursor-pointer text-xs">Message exact reçu</summary><pre class="payload">{{ JSON.stringify(selected.request, null, 2) }}</pre></details>
      </div>
    </BaseModal>
    <BaseModal v-model="showAssignment" title="Réaffecter la RFQ reçue" max-width="520px">
      <div class="space-y-3"><AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage><label class="block"><span class="label">Collaborateur habilité du desk</span><select v-model.number="assignedTo" class="select w-full"><option v-for="user in assignees" :key="user.id" :value="user.id">{{ user.name }}</option></select></label><label class="block"><span class="label">Motif de réaffectation</span><textarea v-model="assignmentReason" class="input w-full" maxlength="500" rows="3" /></label></div>
      <template #footer><button class="btn-secondary" :disabled="assigning" @click="showAssignment = false">Annuler</button><button class="btn-primary" :disabled="assigning || assignmentReason.trim().length < 3 || !assignedTo" @click="assign">Réaffecter</button></template>
    </BaseModal>
  </div>
</template>

<style scoped>
.payload { margin-top: .5rem; padding: .75rem; background: var(--surface2); border-radius: var(--radius-sm); font-size: .7rem; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
