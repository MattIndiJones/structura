<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch, apiErrorMessage } from '../utils/api'
import { formatDate, formatNumber } from '../utils/format.js'
import BackLink from '../components/ui/BackLink.vue'

const relations = ref([])
const executions = ref([])
const counterparties = ref([])
const positions = ref(null)
const error = ref('')
const busy = ref(false)
const refreshing = ref(false)
const editing = ref(null)
const showForm = ref(false)
const proofs = ref({})

const empty = () => ({
  counterparty_id: null,
  reference: '',
  status: 'PENDING',
  effective_date: new Date().toISOString().slice(0, 10),
  expiry_date: null,
  currency: 'EUR',
  note_distribution_allowed: true,
  otc_allowed: false,
  documentation_reference: '',
  gross_notional_limit: 100_000_000,
  master_agreement_id: null,
  csa_id: null,
  csa_required: false,
  settlement: 'DVP',
  notes: '',
})

const form = ref(empty())
const grossLimitInput = ref('100 000 000')
const activeCount = computed(() => relations.value.filter(row => row.status === 'ACTIVE').length)
const pendingCount = computed(() => executions.value.filter(row => row.settlement_status === 'PENDING').length)

const relationshipStates = {
  PENDING: 'En préparation',
  ACTIVE: 'Active',
  SUSPENDED: 'Suspendue',
  EXPIRED: 'Expirée',
}

async function api(path, options = {}) {
  const res = await apiFetch('/api' + path, {
    ...options,
    headers: options.body ? { 'Content-Type': 'application/json' } : {},
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(apiErrorMessage(body))
  return body
}

async function load() {
  refreshing.value = true
  try {
    [relations.value, executions.value, counterparties.value, positions.value] = await Promise.all([
      api('/trading/relationships'),
      api('/trading/executions'),
      api('/deals/counterparties'),
      api('/trading/positions'),
    ])
    error.value = ''
  } catch (failure) {
    error.value = failure.message
  } finally {
    refreshing.value = false
  }
}

function amount(value) {
  if (value === null || value === undefined || value === '') return '—'
  const decimals = (String(value).split('.')[1] || '').length
  return formatNumber(value, Math.min(decimals, 8))
}

function parseAmount(text) {
  const raw = String(text).replace(/[\s\u00a0\u202f]/g, '').replace(',', '.')
  if (!/^\d+(?:\.\d+)?$/.test(raw)) return null
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : null
}

function onGrossLimitInput(event) {
  grossLimitInput.value = event.target.value
  form.value.gross_notional_limit = parseAmount(grossLimitInput.value)
}

function normalizeGrossLimit() {
  if (form.value.gross_notional_limit !== null) {
    grossLimitInput.value = amount(form.value.gross_notional_limit)
  }
}

function startCreate() {
  editing.value = null
  form.value = empty()
  grossLimitInput.value = amount(form.value.gross_notional_limit)
  showForm.value = true
  error.value = ''
}

function edit(row) {
  editing.value = row.id
  form.value = { ...row }
  delete form.value.id
  delete form.value.version
  grossLimitInput.value = amount(row.gross_notional_limit)
  showForm.value = true
  error.value = ''
}

function closeForm() {
  showForm.value = false
  editing.value = null
  form.value = empty()
  grossLimitInput.value = amount(form.value.gross_notional_limit)
}

async function save() {
  if (form.value.gross_notional_limit === null) {
    error.value = 'Le plafond doit être un montant positif. Utilisez des espaces pour les milliers et une virgule pour les décimales.'
    return
  }
  busy.value = true
  try {
    const row = relations.value.find(item => item.id === editing.value)
    const data = { ...form.value, expiry_date: form.value.expiry_date || null }
    if (row) data.expected_version = row.version
    await api('/trading/relationships' + (row ? '/' + row.id : ''), {
      method: row ? 'PUT' : 'POST',
      body: JSON.stringify(data),
    })
    closeForm()
    await load()
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}

async function settle(row) {
  busy.value = true
  try {
    await api('/trading/executions/' + row.id + '/settle', {
      method: 'POST',
      body: JSON.stringify({ reference: proofs.value[row.id] }),
    })
    delete proofs.value[row.id]
    await load()
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}

function counterpartyName(id) {
  return counterparties.value.find(row => row.id === id)?.name || 'Contrepartie #' + id
}

onMounted(load)
</script>

<template>
  <div class="trading-page">
    <header class="trading-header">
      <div class="flex items-start gap-3 min-w-0">
        <BackLink fallback="/" />
        <div>
          <h1 class="text-xl font-bold">Relations et exécutions</h1>
          <p class="text-xs text-slate-500">Accords de distribution, notes bookées et suivi de leur règlement</p>
        </div>
      </div>
      <button class="btn-secondary btn-sm" :disabled="refreshing" @click="load">
        {{ refreshing ? 'Actualisation…' : 'Actualiser' }}
      </button>
    </header>

    <main class="trading-scroll">
      <div class="trading-content">
        <section class="card trading-guide" aria-label="À quoi sert cette page">
          <div>
            <h2>Comment utiliser cette page</h2>
            <p>Cette page suit les notes après la demande de prix. Une relation définit les conditions de booking de votre entité avec une contrepartie. Elle ne constitue pas un envoi de RFQ à cette banque.</p>
          </div>
          <ol class="steps">
            <li><strong>1. Définir la relation</strong><span>Contrepartie, documentation, devise et plafond autorisé.</span></li>
            <li><strong>2. Booker la note</strong><span>Dans <RouterLink to="/pricer" class="text-blue-600 underline">Pricer → Deal</RouterLink>, choisir la relation et inscrire l’exécution au journal.</span></li>
            <li><strong>3. Suivre le règlement</strong><span>Consulter le journal, puis enregistrer une référence de preuve quand le cash a effectivement été réglé.</span></li>
          </ol>
        </section>

        <p v-if="error" class="p-3 bg-red-950 text-red-200 rounded" role="alert">{{ error }}</p>

        <div class="trading-stats" aria-label="Vue d’ensemble">
          <div class="card"><strong>{{ amount(relations.length) }}</strong><span>relations, dont {{ amount(activeCount) }} actives</span></div>
          <div class="card"><strong>{{ amount(executions.length) }}</strong><span>notes inscrites au journal</span></div>
          <div class="card"><strong>{{ amount(pendingCount) }}</strong><span>règlements à rapprocher</span></div>
        </div>

        <section class="card" aria-labelledby="relationships-title">
          <div class="section-heading">
            <div>
              <h2 id="relationships-title">1 · Relations avec les contreparties</h2>
              <p>Ces conditions sont enregistrées pour votre entité. Une relation active et dans son périmètre est requise pour inscrire une note au journal.</p>
            </div>
            <button class="btn-primary btn-sm" @click="startCreate">Nouvelle relation</button>
          </div>
          <div class="table-scroll">
            <table>
              <thead><tr><th>Contrepartie et référence</th><th>État et dates</th><th>Opérations autorisées</th><th>Plafond brut</th><th></th></tr></thead>
              <tbody>
                <tr v-for="row in relations" :key="row.id">
                  <td><strong>{{ counterpartyName(row.counterparty_id) }}</strong><small>{{ row.reference }} · version {{ row.version }}</small></td>
                  <td><span class="state" :class="'state-' + row.status.toLowerCase()">{{ relationshipStates[row.status] || row.status }}</span><small>Effet {{ formatDate(row.effective_date) }}<template v-if="row.expiry_date"> · fin {{ formatDate(row.expiry_date) }}</template></small></td>
                  <td>{{ row.note_distribution_allowed ? 'Notes' : 'Notes non autorisées' }}<template v-if="row.otc_allowed"> · OTC</template><small v-if="row.csa_required">CSA requis</small></td>
                  <td class="numeric">{{ amount(row.gross_notional_limit) }} {{ row.currency }}</td>
                  <td><button class="btn-secondary btn-sm" @click="edit(row)">Modifier</button></td>
                </tr>
                <tr v-if="!relations.length"><td colspan="5" class="empty-row">Aucune relation. Créez-en une avant de booker une note dans ce journal.</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <form v-if="showForm" class="card relation-form" aria-label="Conditions de la relation" @submit.prevent="save">
          <div class="section-heading">
            <div><h2>{{ editing ? 'Modifier la relation' : 'Nouvelle relation' }}</h2><p>Les champs ci-dessous fixent le périmètre que le booking contrôlera.</p></div>
            <button type="button" class="btn-secondary btn-sm" @click="closeForm">Fermer</button>
          </div>

          <div class="form-grid">
            <label>Contrepartie
              <select v-model="form.counterparty_id" class="input" required :disabled="!!editing">
                <option :value="null" disabled>Choisir une contrepartie</option>
                <option v-for="row in counterparties" :key="row.id" :value="row.id">{{ row.name }}</option>
              </select>
            </label>
            <label>Référence de l’accord
              <input v-model.trim="form.reference" class="input" required minlength="3" maxlength="100" :disabled="!!editing" />
            </label>
            <label>État de la relation
              <select v-model="form.status" class="input">
                <option value="PENDING">En préparation</option>
                <option value="ACTIVE">Active</option>
                <option value="SUSPENDED">Suspendue</option>
                <option value="EXPIRED">Expirée</option>
              </select>
            </label>
            <label>Date d’effet
              <input v-model="form.effective_date" type="date" required class="input" />
            </label>
            <label>Date de fin, si prévue
              <input v-model="form.expiry_date" type="date" class="input" />
            </label>
            <label>Devise des notes
              <input v-model.trim="form.currency" required maxlength="3" class="input" @input="form.currency = form.currency.toUpperCase()" />
            </label>
            <label>Plafond de nominal brut ({{ form.currency || 'devise' }})
              <input :value="grossLimitInput" type="text" inputmode="decimal" class="input numeric-input" required
                     aria-describedby="gross-limit-hint" @input="onGrossLimitInput" @blur="normalizeGrossLimit" />
              <small id="gross-limit-hint">{{ form.gross_notional_limit === null ? 'Montant positif attendu' : amount(form.gross_notional_limit) + ' ' + form.currency }} · total des nominaux actifs de cette relation</small>
            </label>
            <label>Mode de règlement
              <select v-model="form.settlement" class="input">
                <option value="DVP">Livraison contre paiement (DVP)</option>
                <option value="FREE_OF_PAYMENT">Livraison sans paiement</option>
              </select>
            </label>
          </div>

          <div class="form-options">
            <label><input v-model="form.note_distribution_allowed" type="checkbox" /> Autoriser les notes</label>
            <label><input v-model="form.otc_allowed" type="checkbox" /> Autoriser l’OTC</label>
            <label v-if="form.otc_allowed"><input v-model="form.csa_required" type="checkbox" /> CSA requis pour l’OTC</label>
          </div>
          <div v-if="form.otc_allowed" class="form-grid">
            <p class="field-note">Les accords sont administrés dans <RouterLink to="/ccr" class="text-blue-600 underline">Risque de contrepartie</RouterLink>. Une référence active est exigée pour l’OTC.</p>
            <label>Identifiant de l’accord cadre
              <input v-model.number="form.master_agreement_id" type="number" min="1" required class="input" />
            </label>
            <label>Identifiant du CSA
              <input v-model.number="form.csa_id" type="number" min="1" :required="form.csa_required" class="input" />
            </label>
          </div>
          <label class="full-field">Référence de la documentation signée
            <textarea v-model="form.documentation_reference" class="input" :required="form.status === 'ACTIVE'" maxlength="1000" rows="2" />
            <small>Obligatoire pour activer la relation ; cette référence doit correspondre à celle du deal.</small>
          </label>
          <label class="full-field">Notes internes
            <textarea v-model="form.notes" class="input" maxlength="3000" rows="2" />
          </label>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="closeForm">Annuler</button>
            <button class="btn-primary" :disabled="busy">{{ busy ? 'Enregistrement…' : 'Enregistrer la relation' }}</button>
          </div>
        </form>

        <section class="card" aria-labelledby="executions-title">
          <div class="section-heading">
            <div>
              <h2 id="executions-title">2 · Notes bookées et règlement</h2>
              <p>Le journal est alimenté lors du booking dans Pricer → Deal, lorsque l’option d’inscription à la relation est choisie. Achat et vente décrivent notre entité.</p>
            </div>
            <RouterLink to="/pricer" class="btn-secondary btn-sm">Ouvrir le Pricer</RouterLink>
          </div>
          <p class="field-note mb-3">Saisissez une référence de preuve seulement après confirmation externe du règlement. L’action marque le journal comme réglé ; elle ne déclenche aucun paiement bancaire.</p>
          <div class="table-scroll">
            <table>
              <thead><tr><th>Deal et instrument</th><th>Contrepartie / émetteur</th><th>Notre sens</th><th>Nominal et prix traité</th><th>Règlement</th></tr></thead>
              <tbody>
                <tr v-for="row in executions" :key="row.id">
                  <td><RouterLink :to="'/booking?deal=' + row.deal_id" class="text-blue-600 underline">{{ row.deal_reference }}</RouterLink><small>{{ row.instrument_reference }}</small></td>
                  <td>{{ row.counterparty }}<small>Émetteur : {{ row.issuer }}</small></td>
                  <td>{{ row.our_side === 'BUY' ? 'Nous achetons' : 'Nous vendons' }}</td>
                  <td class="numeric">{{ amount(row.nominal) }} {{ row.currency }}<small>Prix traité : {{ amount(row.price_traded) }} %</small></td>
                  <td>
                    <span class="state" :class="row.settlement_status === 'SETTLED' ? 'state-active' : 'state-pending'">{{ row.settlement_status === 'SETTLED' ? 'Réglé' : 'À rapprocher' }}</span>
                    <small>Valeur {{ formatDate(row.value_date) }}</small>
                    <form v-if="row.settlement_status === 'PENDING'" class="proof-form" @submit.prevent="settle(row)">
                      <input v-model.trim="proofs[row.id]" class="input" placeholder="Référence de preuve" aria-label="Référence de preuve de règlement" minlength="5" maxlength="200" required />
                      <button class="btn-secondary btn-sm" :disabled="busy">Enregistrer la preuve</button>
                    </form>
                    <small v-else>Preuve : {{ row.settlement_reference }}</small>
                  </td>
                </tr>
                <tr v-if="!executions.length"><td colspan="5" class="empty-row">Aucune note inscrite. Le booking se lance depuis le Pricer après choix d’une relation active.</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="positions" class="card" aria-labelledby="positions-title">
          <div class="section-heading">
            <div>
              <h2 id="positions-title">3 · Positions issues du journal</h2>
              <p>Par instrument et émetteur. Nominal positif : notes achetées ou détenues ; négatif : notes vendues ou émises. Cash positif : à recevoir ; négatif : à verser.</p>
            </div>
          </div>
          <p class="field-note mb-3">{{ positions.risk_definition }}</p>
          <div class="table-scroll">
            <table>
              <thead><tr><th>Instrument</th><th>Émetteur</th><th>Nominal net</th><th>Cash à régler</th></tr></thead>
              <tbody>
                <tr v-for="row in positions.positions" :key="row.instrument_reference + row.issuer">
                  <td>{{ row.instrument_reference }}</td><td>{{ row.issuer }}</td>
                  <td class="numeric">{{ amount(row.nominal) }} {{ row.currency }}</td>
                  <td class="numeric">{{ amount(row.pending_cash) }} {{ row.currency }}</td>
                </tr>
                <tr v-if="!positions.positions.length"><td colspan="4" class="empty-row">Aucune position issue du journal.</td></tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.trading-page { flex: 1; min-height: 0; min-width: 0; display: flex; flex-direction: column; overflow: hidden; color: var(--text); }
.trading-header { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .75rem; padding: 1rem 1.5rem; border-bottom: 1px solid var(--border); }
.trading-scroll { flex: 1; min-height: 0; min-width: 0; overflow: auto; overscroll-behavior: contain; }
.trading-content { max-width: 1500px; margin: 0 auto; padding: 1.25rem 1.5rem 2rem; display: flex; flex-direction: column; gap: 1rem; }
.trading-guide { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: 1.5rem; }
.trading-guide p, .section-heading p { margin-top: .3rem; color: var(--muted); font-size: .78rem; line-height: 1.45; }
.steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .7rem; }
.steps li { display: flex; flex-direction: column; gap: .25rem; border-left: 2px solid var(--border2); padding-left: .7rem; font-size: .76rem; }
.steps strong { font-size: .78rem; }
.steps span { color: var(--muted); line-height: 1.4; }
.trading-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
.trading-stats .card { padding: .75rem 1rem; display: flex; align-items: baseline; gap: .65rem; }
.trading-stats strong { font-size: 1.3rem; font-variant-numeric: tabular-nums; }
.trading-stats span { color: var(--muted); font-size: .75rem; }
.section-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: .75rem; margin-bottom: .8rem; }
.section-heading h2, .trading-guide h2 { font-size: 1rem; font-weight: 700; }
.section-heading .btn-primary, .section-heading .btn-secondary { flex-shrink: 0; }
.table-scroll { overflow-x: auto; overscroll-behavior: contain; }
table { width: 100%; min-width: 690px; font-size: .76rem; }
th, td { text-align: left; padding: .65rem .5rem; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; white-space: nowrap; }
td small { display: block; color: var(--muted); font-size: .7rem; margin-top: .25rem; }
.empty-row { color: var(--muted); text-align: center; padding: 1.5rem; }
.numeric, .numeric-input { font-variant-numeric: tabular-nums; white-space: nowrap; }
.state { display: inline-block; padding: .2rem .45rem; border-radius: .35rem; font-size: .7rem; font-weight: 600; white-space: nowrap; }
.state-active { color: #047857; background: #d1fae5; }
.state-pending { color: #92400e; background: #fef3c7; }
.state-suspended { color: #9a3412; background: #ffedd5; }
.state-expired { color: #475569; background: #e2e8f0; }
.relation-form { display: flex; flex-direction: column; gap: .8rem; }
.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
.relation-form label { display: flex; flex-direction: column; gap: .3rem; font-size: .76rem; font-weight: 600; }
.relation-form .input { width: 100%; min-width: 0; font-weight: 400; }
.relation-form small, .field-note { color: var(--muted); font-size: .72rem; line-height: 1.4; font-weight: 400; }
.form-options { display: flex; flex-wrap: wrap; gap: 1rem; }
.form-options label { flex-direction: row; align-items: center; }
.full-field { width: 100%; }
.form-actions { display: flex; justify-content: flex-end; gap: .5rem; }
.proof-form { display: flex; flex-direction: column; gap: .35rem; margin-top: .4rem; min-width: 180px; }
.proof-form .input { width: 100%; }
@media (max-width: 900px) { .trading-guide { grid-template-columns: 1fr; } .form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .trading-header { padding: .75rem 1rem; } .trading-content { padding: 1rem; } .steps, .trading-stats, .form-grid { grid-template-columns: 1fr; } .section-heading { flex-wrap: wrap; } }
</style>
