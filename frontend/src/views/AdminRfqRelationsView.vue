<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import { formatDate, formatDateTime, formatNumber } from '../utils/format.js'
import { PAYOFF_FAMILIES } from '../utils/payoffFamilies.js'
import BaseModal from '../components/ui/BaseModal.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import RfqNetworkSettings from '../components/RfqNetworkSettings.vue'

const rows = ref([])
const catalog = ref({ organizations: [], desks: [], counterparties: [], trading_relationships: [] })
const error = ref('')
const notice = ref('')
const loading = ref(true)
const busy = ref(false)
const showForm = ref(false)
const editing = ref(null)
const decision = ref(null)
const showDecision = ref(false)
const showHistory = ref(false)
const history = ref([])
const historyCursor = ref(null)
const historyRow = ref(null)
const form = reactive({})
const minAmount = ref('')
const maxAmount = ref('')
const states = { PENDING: 'À reconnaître', ACTIVE: 'Active', SUSPENDED: 'Suspendue', EXPIRED: 'Expirée', NOT_STARTED: 'Effet futur' }
const actions = { RFQ_RELATIONSHIP_CREATED: 'Création', RFQ_RELATIONSHIP_UPDATED: 'Modification', RFQ_RELATIONSHIP_RECOGNIZED: 'Reconnaissance', RFQ_RELATIONSHIP_SUSPENDED: 'Suspension', RFQ_RELATIONSHIP_RESUMED: 'Reprise' }
const partnerDesks = computed(() => catalog.value.desks.filter(d => d.entity_id === form.partner_entity_id))
const bookingOptions = computed(() => catalog.value.trading_relationships.filter(r => r.counterparty_id === form.counterparty_id))
const decisionReason = ref('')
const modalError = ref('')
const today = () => { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }
const items = value => [...new Set(value.split(',').map(s => s.trim()).filter(Boolean))]
const displayBound = value => value === null ? 'Sans borne' : formatNumber(value, 0)

async function api(path, options) {
  const res = await apiFetch(`/api/rfq-relations${path}`, options ? {
    ...options, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options.body),
  } : undefined)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = data.detail
    throw new Error(typeof detail === 'string' ? detail : detail?.message || 'Opération refusée. Vérifiez les champs et votre organisation.')
  }
  return data
}

async function load() {
  loading.value = true
  error.value = ''
  try { [catalog.value, rows.value] = await Promise.all([api('/catalog'), api('')]) }
  catch (failure) { error.value = failure.message }
  finally { loading.value = false }
}
onMounted(load)

function configure(row = null) {
  editing.value = row
  const terms = row?.terms || {}
  Object.assign(form, {
    requester_entity_id: row?.requester_entity_id ?? catalog.value.entity_id,
    partner_entity_id: row?.partner_entity_id ?? null, receiver_desk_id: row?.receiver_desk_id ?? null,
    reference: row?.reference || '', counterparty_id: row?.local.counterparty_id ?? null,
    trading_relationship_id: row?.local.trading_relationship_id ?? null,
    formats: (terms.formats || []).join(', '), instruments: (terms.instruments || []).join(', '),
    currencies: (terms.currencies || []).join(', '), payoff_families: [...terms.payoff_families || []],
    effective_date: terms.effective_date || today(), expiry_date: terms.expiry_date || '',
    solicitation_allowed: terms.solicitation_allowed ?? false, indicative_allowed: terms.indicative_allowed ?? true,
    to_trade_allowed: terms.to_trade_allowed ?? false, treatment_allowed: terms.treatment_allowed ?? false,
    documentation_reference: terms.documentation_reference || '',
    contacts: (row?.local.contacts || []).map(c => ({ ...c })), reason: '',
  })
  minAmount.value = terms.min_notional == null ? '' : formatNumber(terms.min_notional, 0)
  maxAmount.value = terms.max_notional == null ? '' : formatNumber(terms.max_notional, 0)
  modalError.value = ''
  showForm.value = true
}

function parseBound(value) {
  if (!value.trim()) return null
  const plain = value.replace(/[\s\u00a0\u202f]/g, '').replace(',', '.')
  const number = /^\d+(\.\d+)?$/.test(plain) ? Number(plain) : NaN
  if (!Number.isFinite(number) || number <= 0) throw new Error('Les bornes de nominal doivent être positives ; les espaces séparent les milliers.')
  return number
}

function formatBound(input) {
  try { const value = parseBound(input); const decimals = (input.replace(',', '.').split('.')[1] || '').length; return value == null ? '' : decimals > 20 ? input : formatNumber(value, decimals) }
  catch { return input }
}

async function save() {
  modalError.value = ''
  busy.value = true
  try {
    const terms = { formats: items(form.formats), instruments: items(form.instruments),
      currencies: items(form.currencies), payoff_families: [...form.payoff_families],
      min_notional: parseBound(minAmount.value), max_notional: parseBound(maxAmount.value),
      effective_date: form.effective_date, expiry_date: form.expiry_date || null,
      solicitation_allowed: form.solicitation_allowed, indicative_allowed: form.indicative_allowed,
      to_trade_allowed: form.to_trade_allowed, treatment_allowed: form.treatment_allowed,
      documentation_reference: form.documentation_reference, policy: 'RFQ_V1' }
    const body = { receiver_desk_id: form.receiver_desk_id, terms, counterparty_id: form.counterparty_id,
      trading_relationship_id: form.trading_relationship_id, contacts: form.contacts, reason: form.reason }
    if (editing.value) body.expected_version = editing.value.version
    else Object.assign(body, { requester_entity_id: form.requester_entity_id, partner_entity_id: form.partner_entity_id, reference: form.reference })
    await api(editing.value ? `/${editing.value.id}` : '', { method: editing.value ? 'PUT' : 'POST', body })
    showForm.value = false
    notice.value = 'Relation enregistrée ; chaque partie doit reconnaître la version courante.'
    await load()
  } catch (failure) { modalError.value = failure.message }
  finally { busy.value = false }
}

function decide(row, type) {
  decision.value = { row, type }
  decisionReason.value = ''
  modalError.value = ''
  showDecision.value = true
}

async function applyDecision() {
  busy.value = true
  modalError.value = ''
  try {
    const { row, type } = decision.value
    const body = { expected_version: row.version, reason: decisionReason.value }
    if (type !== 'recognize') body.suspended = type === 'suspend'
    await api(`/${row.id}/${type === 'recognize' ? 'recognize' : 'suspension'}`, { method: 'POST', body })
    showDecision.value = false
    notice.value = type === 'recognize' ? 'Votre organisation a reconnu cette version.' : 'État de la relation enregistré.'
    await load()
  } catch (failure) { modalError.value = failure.message }
  finally { busy.value = false }
}

async function openHistory(row) {
  historyRow.value = row
  history.value = []
  modalError.value = ''
  showHistory.value = true
  await fetchHistory()
}

async function fetchHistory(older = false) {
  busy.value = true
  try {
    const page = await api(`/${historyRow.value.id}/history${older ? `?before_id=${historyCursor.value}` : ''}`)
    history.value.push(...page.entries)
    historyCursor.value = page.next_before_id
  } catch (failure) { modalError.value = failure.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="flex-1 min-h-0 flex flex-col overflow-hidden">
    <header class="page-header px-4 sm:px-6 pt-4 pb-3 mb-0 shrink-0 flex-wrap gap-2">
      <div><h1 class="page-title">Relations RFQ</h1><p class="page-subtitle">{{ catalog.organization_name || 'Organisation' }} · partenaires autorisés pour les demandes de prix</p></div>
      <div class="page-actions"><RouterLink to="/admin" class="btn-ghost btn-sm">← Administration</RouterLink>
        <button class="btn-primary btn-sm" :disabled="loading || !catalog.entity_id" @click="configure()">Nouvelle relation RFQ</button></div>
    </header>
    <main class="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 sm:px-6 pb-6 space-y-4">
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <AlertMessage v-if="notice" kind="success" dismissible @dismiss="notice = ''">{{ notice }}</AlertMessage>
      <p class="text-xs text-slate-500">Chaque relation est reconnue par les deux organisations. Les accords de booking restent gérés dans <RouterLink to="/trading" class="underline">Relations et exécutions</RouterLink>.</p>
      <LoadingSpinner v-if="loading" />
      <RfqNetworkSettings v-if="!loading" :relations="rows" :counterparties="catalog.counterparties" :entity-id="catalog.entity_id" @changed="load" />
      <div v-else class="card table-shell">
        <table class="w-full text-xs min-w-[850px]">
          <thead><tr><th>Relation et direction</th><th>État</th><th>Périmètre</th><th>Reconnaissance</th><th>Actions</th></tr></thead>
          <tbody><tr v-for="row in rows" :key="row.id">
            <td><strong>{{ row.reference }}</strong><div>{{ row.requester_name }} → {{ row.partner_name }}</div><div class="text-slate-500">{{ row.receiver_desk_name }} · version {{ row.version }}</div></td>
            <td><span class="badge" :class="row.status === 'ACTIVE' ? 'badge-accent' : 'badge-muted'">{{ states[row.status] }}</span><div class="text-slate-500 mt-1">{{ formatDate(row.terms.effective_date) }}<template v-if="row.terms.expiry_date"> → {{ formatDate(row.terms.expiry_date) }}</template></div></td>
            <td><div>{{ row.terms.formats.join(', ') }} · {{ row.terms.instruments.join(', ') }}</div><div>{{ row.terms.payoff_families.join(', ') }}</div><div>{{ row.terms.currencies.join(', ') }} · {{ displayBound(row.terms.min_notional) }} → {{ displayBound(row.terms.max_notional) }}</div><div>{{ row.terms.solicitation_allowed ? 'Prix autorisé' : 'Sollicitation bloquée' }} · {{ row.terms.treatment_allowed ? 'Traitement autorisé' : 'Traitement non autorisé' }}</div></td>
            <td><div v-for="party in row.recognitions" :key="party.entity_id">{{ party.organization }} · {{ party.suspended ? 'suspendu' : party.recognized ? 'reconnu' : 'en attente' }}</div></td>
            <td><div class="flex flex-wrap gap-1 max-w-[230px]">
              <button class="btn-secondary btn-sm" @click="configure(row)">Configurer</button>
              <button v-if="!row.local.recognized && !row.local.suspended && row.status !== 'EXPIRED'" class="btn-primary btn-sm" @click="decide(row, 'recognize')">Reconnaître</button>
              <button class="btn-secondary btn-sm" @click="decide(row, row.local.suspended ? 'resume' : 'suspend')">{{ row.local.suspended ? 'Reprendre' : 'Suspendre' }}</button>
              <button class="btn-ghost btn-sm" @click="openHistory(row)">Historique</button>
            </div></td>
          </tr><tr v-if="!rows.length"><td colspan="5" class="py-8 text-center text-slate-500">Aucune relation RFQ pour votre organisation.</td></tr></tbody>
        </table>
      </div>
    </main>

    <BaseModal v-model="showForm" :title="editing ? `Configurer ${editing.reference} · v${editing.version}` : 'Nouvelle relation RFQ'" max-width="850px">
      <form id="rfq-relation-form" class="space-y-4" @submit.prevent="save">
        <AlertMessage v-if="modalError" kind="error">{{ modalError }}</AlertMessage>
        <p class="text-xs text-slate-500">Toute modification crée une nouvelle version et demande une nouvelle reconnaissance aux deux parties.</p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label><span class="label">Organisation demandeuse</span><select v-model.number="form.requester_entity_id" class="select w-full" required :disabled="!!editing" @change="form.partner_entity_id = null; form.receiver_desk_id = null"><option v-for="org in catalog.organizations" :key="org.id" :value="org.id">{{ org.name }}</option></select></label>
          <label><span class="label">Organisation répondante</span><select v-model.number="form.partner_entity_id" class="select w-full" required :disabled="!!editing" @change="form.receiver_desk_id = null"><option :value="null">— Choisir —</option><option v-for="org in catalog.organizations.filter(o => o.id !== form.requester_entity_id && (form.requester_entity_id === catalog.entity_id || o.id === catalog.entity_id))" :key="org.id" :value="org.id">{{ org.name }}</option></select></label>
          <label><span class="label">Desk de réception</span><select v-model.number="form.receiver_desk_id" class="select w-full" required><option :value="null">— Choisir —</option><option v-for="desk in partnerDesks" :key="desk.id" :value="desk.id">{{ desk.name }}</option></select></label>
          <label><span class="label">Référence de relation</span><input v-model="form.reference" class="input w-full" required minlength="3" :disabled="!!editing" /></label>
          <label><span class="label">Contrepartie juridique dans votre référentiel</span><select v-model.number="form.counterparty_id" required class="select w-full" @change="form.trading_relationship_id = null"><option :value="null">— Rapprocher explicitement —</option><option v-for="c in catalog.counterparties" :key="c.id" :value="c.id">{{ c.name }}</option></select></label>
          <label><span class="label">Formats autorisés · séparés par virgules</span><input v-model="form.formats" class="input w-full" placeholder="EMTN, OTC" required /></label>
          <label><span class="label">Instruments autorisés</span><input v-model="form.instruments" class="input w-full" placeholder="Note, Swap" required /></label>
          <label><span class="label">Devises autorisées</span><input v-model="form.currencies" class="input w-full" placeholder="EUR, USD" required /></label>
          <div><span class="label">Familles de payoff autorisées</span><div class="max-h-32 overflow-y-auto overscroll-contain border rounded p-2 flex flex-wrap gap-2"><label v-for="family in PAYOFF_FAMILIES" :key="family.code" class="text-xs flex items-center gap-1"><input v-model="form.payoff_families" type="checkbox" :value="family.label" />{{ family.label }}</label></div></div>
          <label><span class="label">Nominal minimum · facultatif</span><input v-model="minAmount" class="input w-full" inputmode="decimal" placeholder="Sans minimum" @blur="minAmount = formatBound(minAmount)" /></label>
          <label><span class="label">Nominal maximum · facultatif</span><input v-model="maxAmount" class="input w-full" inputmode="decimal" placeholder="Sans maximum" @blur="maxAmount = formatBound(maxAmount)" /></label>
          <label><span class="label">Date d'effet</span><input v-model="form.effective_date" type="date" class="input w-full" required /></label>
          <label><span class="label">Expiration éventuelle</span><input v-model="form.expiry_date" type="date" class="input w-full" /></label>
        </div>
        <div class="flex flex-wrap gap-4 text-xs">
          <label class="flex items-center gap-1"><input v-model="form.solicitation_allowed" type="checkbox" />Autoriser les demandes de prix</label>
          <label class="flex items-center gap-1"><input v-model="form.indicative_allowed" type="checkbox" />Indicatif</label>
          <label class="flex items-center gap-1"><input v-model="form.to_trade_allowed" type="checkbox" />To trade</label>
          <label class="flex items-center gap-1"><input v-model="form.treatment_allowed" type="checkbox" />Autoriser le traitement</label>
        </div>
        <div class="grid sm:grid-cols-2 gap-3">
          <label><span class="label">Documentation partagée</span><input v-model="form.documentation_reference" class="input w-full" :required="form.treatment_allowed" /></label>
          <label><span class="label">Accord de booking local · requis pour traiter</span><select v-model.number="form.trading_relationship_id" class="select w-full" :required="form.treatment_allowed"><option :value="null">— Aucun —</option><option v-for="r in bookingOptions" :key="r.id" :value="r.id">{{ r.reference }} · {{ r.status }}</option></select></label>
        </div>
        <div class="space-y-2"><div class="flex items-center justify-between"><span class="label mb-0">Vos contacts partagés</span><button type="button" class="btn-ghost btn-sm" @click="form.contacts.push({ name: '', email: '' })">Ajouter un contact</button></div>
          <div v-for="(contact, index) in form.contacts" :key="index" class="flex flex-wrap gap-2"><input v-model="contact.name" class="input flex-1 min-w-0" placeholder="Nom" required /><input v-model="contact.email" type="email" class="input flex-1 min-w-0" placeholder="E-mail facultatif" /><button type="button" class="btn-ghost btn-sm" @click="form.contacts.splice(index, 1)">Retirer</button></div>
        </div>
        <p class="text-xs text-slate-500">Règles RFQ V1 : fermeté révocable avant réception d'une acceptation valide ; réception horodatée par Structura faisant foi ; confirmation explicite avant booking. Une contestation après acceptation exige une revue manuelle.</p>
        <label class="block"><span class="label">Motif de création ou de modification</span><input v-model="form.reason" class="input w-full" required minlength="3" /></label>
      </form>
      <template #footer><button class="btn-secondary" @click="showForm = false">Annuler</button><button type="submit" form="rfq-relation-form" class="btn-primary" :disabled="busy">{{ busy ? 'Enregistrement…' : 'Enregistrer la version' }}</button></template>
    </BaseModal>
    <BaseModal v-model="showDecision" :title="decision?.type === 'recognize' ? 'Reconnaître la relation RFQ' : decision?.type === 'resume' ? 'Reprendre la relation' : 'Suspendre la relation'" max-width="550px">
      <div class="space-y-3"><AlertMessage v-if="modalError" kind="error">{{ modalError }}</AlertMessage>
        <p class="text-sm">{{ decision?.row.reference }} · version {{ decision?.row.version }} · {{ catalog.organization_name }}</p>
        <p class="text-xs text-slate-500">{{ decision?.type === 'recognize' ? 'Vous reconnaissez les termes exacts de cette version pour votre organisation. L’autre partie doit aussi les reconnaître.' : decision?.type === 'resume' ? 'Une reprise exige ensuite votre reconnaissance explicite de la version courante.' : 'La suspension bloque les nouvelles sollicitations. Les demandes et accords antérieurs sont conservés.' }}</p>
        <label><span class="label">Motif</span><input v-model="decisionReason" class="input w-full" /></label>
      </div><template #footer><button class="btn-secondary" @click="showDecision = false">Annuler</button><button class="btn-primary" :disabled="busy || decisionReason.trim().length < 3" @click="applyDecision">Confirmer</button></template>
    </BaseModal>
    <BaseModal v-model="showHistory" :title="`Historique · ${historyRow?.reference || ''}`" max-width="750px">
      <div class="space-y-3"><AlertMessage v-if="modalError" kind="error">{{ modalError }}</AlertMessage>
        <div v-for="event in history" :key="event.id" class="border-b pb-2 text-xs"><strong>{{ actions[event.action] || event.action }} · version {{ event.after.version }}</strong><p>{{ formatDateTime(event.at) }} · {{ event.actor }}</p><p>{{ event.reason }}</p></div>
        <button v-if="historyCursor" class="btn-secondary btn-sm" :disabled="busy" @click="fetchHistory(true)">Charger les événements précédents</button>
      </div>
    </BaseModal>
  </div>
</template>
