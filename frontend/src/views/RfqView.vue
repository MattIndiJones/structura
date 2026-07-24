<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">

    <div class="page-header px-6 pt-6 pb-0 mb-0">
      <div>
        <h1 class="page-title">RFQ Fournisseurs</h1>
      </div>
      <div class="page-actions">
        <RouterLink to="/rfq/analyse" class="btn-ghost btn-sm">📈 Analyse</RouterLink>
        <button class="btn-primary text-xs px-3 py-1.5" @click="openCreateForm">+ Nouvelle RFQ</button>
      </div>
    </div>

    <div class="flex flex-1 min-h-0">

      <!-- ── Liste RFQ ──────────────────────────────────────────── -->
      <aside class="w-80 shrink-0 border-r border-slate-800 overflow-y-auto p-3 flex flex-col gap-2">
        <LoadingSpinner v-if="loadingList" class="py-4" />
        <EmptyState v-else-if="!rfq.list.length" icon="📨" title="Aucune RFQ pour l'instant" />
        <div v-for="r in rfq.list" :key="r.id"
             :class="['card p-3 flex flex-col gap-1.5 cursor-pointer transition-all duration-200 hover:shadow-lg hover:shadow-black/20',
                      selectedId === r.id ? 'border-blue-600 shadow-lg shadow-blue-950/30' : 'hover:border-slate-700']"
             @click="selectRfq(r.id)">
          <div class="flex items-start justify-between gap-2">
            <span class="font-semibold text-slate-200 text-sm truncate">{{ r.name || r.reference }}</span>
            <div class="flex items-center gap-1.5 shrink-0">
              <span :class="['text-[9px] rounded px-1.5 py-0.5 border', statusBadge(r.status)]">{{ statusLabel(r.status) }}</span>
              <button class="text-slate-600 hover:text-red-400" title="Supprimer" @click.stop="deleteRfq(r.id)">🗑</button>
            </div>
          </div>
          <div class="text-[10px] text-slate-600 font-mono">{{ r.reference }} · AO {{ fmtDateOnly(r.ao_date) }}</div>
          <div class="flex items-center gap-3 text-[10px] text-slate-500 mt-1">
            <span v-if="r.model_price !== null">Modèle: {{ fmtPrice(r.model_price) }}</span>
            <span v-else class="text-slate-700">Modèle: —</span>
          </div>
        </div>
      </aside>

      <!-- ── Panneau principal ──────────────────────────────────── -->
      <main class="flex-1 overflow-y-auto p-6">

        <!-- Formulaire de création -->
        <div v-if="showCreateForm" class="max-w-2xl flex flex-col gap-4">
          <h2 class="text-sm font-bold text-slate-300 uppercase tracking-wider">Nouvelle RFQ</h2>

          <AlertMessage v-if="createError" kind="error">{{ createError }}</AlertMessage>

          <div class="card flex flex-col gap-3">
            <div class="grid grid-cols-2 gap-3">
              <div class="flex flex-col gap-1">
                <label class="label">Nom *</label>
                <input v-model="form.name" type="text" class="input" placeholder="Autocall Athena USD 3Y — Client X" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Date de l'AO</label>
                <input v-model="form.ao_date" type="date" class="input" />
              </div>
            </div>

            <div class="flex items-center gap-1 text-[10px] border border-slate-700 rounded overflow-hidden w-fit">
              <button :class="['px-2 py-1 transition-colors', form.source === 'template' ? 'bg-slate-700 text-slate-200 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                      @click="onSourceToggle('template')">Template no-code</button>
              <button :class="['px-2 py-1 transition-colors', form.source === 'script' ? 'bg-blue-900/80 text-blue-300 font-semibold' : 'text-slate-500 hover:text-slate-400']"
                      @click="onSourceToggle('script')">Script existant</button>
            </div>

            <div v-if="form.source === 'template'" class="flex flex-col gap-1">
              <label class="label">Type de produit</label>
              <select v-model="form.template_type" class="select" @change="onTemplateChange">
                <option value="">Choisir un template…</option>
                <optgroup v-for="(items, group) in groupedTemplates" :key="group" :label="group">
                  <option v-for="t in items" :key="t.key" :value="t.key">{{ t.label }}</option>
                </optgroup>
              </select>
            </div>
            <div v-else class="flex flex-col gap-1">
              <label class="label">Script de la bibliothèque</label>
              <select v-model="form.script_id" class="select" @change="onScriptChange">
                <option :value="null">Choisir un script…</option>
                <option v-for="s in scripts" :key="s.id" :value="s.id">{{ s.name }}</option>
              </select>
            </div>

            <!-- Sous-jacent -->
            <div class="grid grid-cols-2 gap-3">
              <div class="flex flex-col gap-1">
                <label class="label">Sous-jacent</label>
                <select class="select" :value="form.underlying_ticker" @change="onUnderlyingSelect($event.target.value)">
                  <option value="">— Choisir un sous-jacent —</option>
                  <optgroup v-for="g in underlyingGroups" :key="g.group" :label="g.group">
                    <option v-for="it in g.items" :key="it.ticker" :value="it.ticker">{{ it.label }}</option>
                  </optgroup>
                </select>
                <input v-model="form.underlying_ticker" type="text" class="input font-mono text-xs mt-1"
                       placeholder="Ticker (ou saisie libre)" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Nominal</label>
                <input v-model="nominalRaw" @blur="formatNominal" @focus="unformatNominal"
                       type="text" inputmode="numeric" class="input font-mono"
                       placeholder="1 000 000" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Devise</label>
                <input v-model="form.currency" type="text" class="input" placeholder="CHF" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Maturité (années)</label>
                <input v-model.number="form.T" type="number" step="0.5" class="input" />
              </div>
            </div>

            <!-- Termes du produit (dynamiques, extraits du script) -->
            <div v-if="parsedParams.length" class="border-t border-slate-800 pt-3 flex flex-col gap-2">
              <div class="label mb-0">Termes du produit</div>
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div v-for="p in parsedParams" :key="p.name" class="flex flex-col gap-1">
                  <label class="label">{{ p.name }}</label>
                  <div class="relative">
                    <input type="number" class="input pr-6" step="any" v-model.number="paramOverrides[p.name]" />
                    <span v-if="p.is_pct" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-500">%</span>
                  </div>
                  <span v-if="p.desc && p.desc !== p.name" class="text-[10px] text-slate-600">{{ p.desc }}</span>
                </div>
              </div>
            </div>

            <!-- Hypothèses de pricing (avancé, pour le calcul du prix modèle interne) -->
            <details class="border-t border-slate-800 pt-3">
              <summary class="label mb-0 cursor-pointer select-none">▸ Hypothèses de pricing (avancé)</summary>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2">
                <div class="flex flex-col gap-1">
                  <label class="label">Vol implicite (%)</label>
                  <input v-model.number="advanced.sigma" type="number" class="input" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Taux sans risque (%)</label>
                  <input v-model.number="advanced.r" type="number" step="0.1" class="input" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Trajectoires (N)</label>
                  <input v-model.number="advanced.N" type="number" step="1000" class="input" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="label">Modèle</label>
                  <select v-model="advanced.model" class="select">
                    <option value="constant">Constant (GBM)</option>
                    <option value="heston">Heston</option>
                    <option value="sabr">SABR</option>
                    <option value="localvol">Dupire (Local Vol)</option>
                    <option value="lsv">Local-Stochastic Vol</option>
                  </select>
                </div>
              </div>
            </details>
          </div>

          <div class="flex gap-2">
            <button class="btn-primary text-sm" :disabled="creating" @click="submitCreate">
              {{ creating ? 'Création…' : 'Créer la RFQ' }}
            </button>
            <button class="btn-secondary text-sm" @click="showCreateForm = false">Annuler</button>
          </div>
        </div>

        <!-- Détail RFQ -->
        <div v-else-if="rfq.current" class="max-w-3xl flex flex-col gap-4">
          <div class="flex items-start justify-between">
            <div>
              <h2 class="text-lg font-bold text-slate-100">{{ rfq.current.name || rfq.current.reference }}</h2>
              <div class="text-xs text-slate-500 font-mono">{{ rfq.current.reference }} · {{ rfq.current.template_type || 'script personnalisé' }}</div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button class="btn-secondary text-xs px-3 py-1.5" title="Créer une nouvelle RFQ à partir de celle-ci"
                      @click="duplicateRfq(rfq.current)">⎘ Dupliquer</button>
              <button class="text-slate-500 hover:text-red-400" title="Supprimer" @click="deleteRfq(rfq.current.id)">🗑</button>
            </div>
          </div>

          <!-- Détails du produit -->
          <div class="card grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <div class="label mb-0.5">Date de l'AO</div>
              <div class="text-xs text-slate-200">{{ fmtDateOnly(rfq.current.ao_date) }}</div>
            </div>
            <div>
              <div class="label mb-0.5">Sous-jacent</div>
              <div class="text-xs text-slate-200">
                {{ underlyingSummary.name || '—' }}
                <span v-if="underlyingSummary.ticker" class="text-slate-500 font-mono">({{ underlyingSummary.ticker }})</span>
              </div>
            </div>
            <div>
              <div class="label mb-0.5">Nominal</div>
              <div class="text-xs text-slate-200">{{ fmtNominal(rfq.current.params?.notional) }} {{ rfq.current.params?.currency || '' }}</div>
            </div>
            <div>
              <div class="label mb-0.5">Maturité</div>
              <div class="text-xs text-slate-200">{{ rfq.current.params?.T ?? '—' }} ans</div>
            </div>
            <div>
              <div class="label mb-0.5">Statut</div>
              <div class="text-xs text-slate-200">{{ statusLabel(rfq.current.status) }}</div>
            </div>
            <div v-for="p in detailParsedParams" :key="p.name">
              <div class="label mb-0.5">{{ p.name }}</div>
              <div class="text-xs text-slate-200">{{ fmtParamValue(p) }}</div>
            </div>
          </div>

          <!-- Prix modèle -->
          <div class="card flex items-center gap-4">
            <div class="stat-box flex-1">
              <div class="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Prix modèle Structura</div>
              <div class="text-xl font-bold text-slate-100">{{ fmtPrice(rfq.current.model_price) }}</div>
              <div v-if="rfq.current.model_price_at" class="text-[10px] text-slate-600 mt-0.5">
                Calculé le {{ fmtDate(rfq.current.model_price_at) }}
              </div>
            </div>
            <button class="btn-secondary text-xs" :disabled="computing" @click="computeModelPrice">
              {{ computing ? 'Calcul…' : 'Calculer prix modèle' }}
            </button>
          </div>
          <AlertMessage v-if="computeError" kind="error">{{ computeError }}</AlertMessage>

          <!-- Script (collapsible) -->
          <details class="card text-xs text-slate-400">
            <summary class="font-bold cursor-pointer text-slate-300 select-none">▸ PayScript</summary>
            <pre class="mt-3 font-mono text-slate-400 whitespace-pre-wrap">{{ rfq.current.script_snapshot }}</pre>
          </details>

          <!-- Quotes -->
          <div class="card flex flex-col gap-3">
            <div class="flex items-center justify-between">
              <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Fournisseurs sollicités</div>
              <button class="btn-secondary text-xs" @click="openAddQuote">+ Ajouter un fournisseur</button>
            </div>

            <div v-if="!rfq.current.quotes?.length" class="text-xs text-slate-600 py-2">
              Aucun fournisseur sollicité pour l'instant.
            </div>

            <div v-else class="table-shell" tabindex="0" role="region">
            <table class="w-full text-xs">
              <thead>
                <tr class="text-left text-slate-500 border-b border-slate-800">
                  <th class="py-1.5 pr-2 font-medium">Fournisseur</th>
                  <th class="py-1.5 pr-2 font-medium">Contact</th>
                  <th class="py-1.5 pr-2 font-medium num">Prix</th>
                  <th class="py-1.5 pr-2 font-medium num">Écart</th>
                  <th class="py-1.5 pr-2 font-medium">Statut</th>
                  <th class="py-1.5 pr-2 font-medium">Date réponse</th>
                  <th class="py-1.5 pr-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="q in rfq.current.quotes" :key="q.id" class="border-b border-slate-800/60">
                  <td class="py-1.5 pr-2 text-slate-300">{{ providerLabel(q.provider) }}</td>
                  <td class="py-1.5 pr-2 text-slate-500">{{ q.contact || '—' }}</td>
                  <td class="py-1.5 pr-2">
                    <input type="number" class="input py-1 px-2 w-24"
                           :value="q.price ?? ''"
                           @change="onQuotePriceChange(q, $event.target.value)" />
                  </td>
                  <td class="py-1.5 pr-2 num" :class="spreadClass(q)">{{ spreadBps(q) }}</td>
                  <td class="py-1.5 pr-2">
                    <select class="select py-1 px-2" :value="q.status" @change="updateQuoteField(q, 'status', $event.target.value)">
                      <option value="en_attente">En attente</option>
                      <option value="recu">Reçu</option>
                      <option value="decline">Décliné</option>
                      <option value="expire">Expiré</option>
                    </select>
                  </td>
                  <td class="py-1.5 pr-2">
                    <input type="datetime-local" class="input py-1 px-2"
                           :value="toDatetimeLocal(q.quoted_at)"
                           @change="onQuoteDateChange(q, $event.target.value)" />
                  </td>
                  <td class="py-1.5 pr-2 text-right">
                    <button class="text-slate-600 hover:text-red-400" @click="removeQuote(q.id)">✕</button>
                  </td>
                </tr>
              </tbody>
            </table>
            </div>

            <!-- Add quote inline form -->
            <div v-if="addingQuote" class="flex items-end gap-2 pt-2 border-t border-slate-800">
              <div class="flex flex-col gap-1">
                <label class="label">Fournisseur</label>
                <select v-model="quoteForm.provider" class="select">
                  <option v-for="p in rfq.providers" :key="p.id" :value="p.label">{{ p.label }}</option>
                  <option value="autre">Autre (banque non listée)</option>
                </select>
              </div>
              <div v-if="quoteForm.provider === 'autre'" class="flex flex-col gap-1">
                <label class="label">Nom de la banque</label>
                <input v-model="quoteForm.customProvider" type="text" class="input" />
              </div>
              <div class="flex flex-col gap-1">
                <label class="label">Contact</label>
                <input v-model="quoteForm.contact" type="text" class="input" placeholder="Nom / email (optionnel)" />
              </div>
              <button class="btn-primary text-xs px-3 py-2" @click="submitAddQuote">Ajouter</button>
              <button class="btn-secondary text-xs px-3 py-2" @click="addingQuote = false">Annuler</button>
            </div>
          </div>
        </div>

        <!-- État vide -->
        <div v-else class="flex flex-col items-center justify-center py-24 gap-3 text-slate-600">
          <div class="text-4xl">📨</div>
          <div class="text-sm">Sélectionnez une RFQ ou créez-en une nouvelle</div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useRfqStore } from '../stores/rfq.js'
import { apiFetch } from '../utils/api.js'
import { templateMeta, examples } from '../data/payscriptTemplates.js'
import { underlyingGroups } from '../data/commonUnderlyings.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import { useToastsStore } from '../stores/toasts.js'

const rfq    = useRfqStore()
const toasts = useToastsStore()

const loadingList    = ref(true)
const selectedId     = ref(null)
const showCreateForm = ref(false)
const creating       = ref(false)
const createError    = ref('')
const computing      = ref(false)
const computeError   = ref('')
const addingQuote    = ref(false)
const scripts        = ref([])

const groupedTemplates = computed(() => {
  const groups = {}
  for (const t of templateMeta) {
    (groups[t.group] ||= []).push(t)
  }
  return groups
})

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

const form = reactive({
  name: '',
  ao_date: todayIso(),
  source: 'template',
  template_type: '',
  script_id: null,
  underlying_name: 'Sous-jacent',
  underlying_ticker: '',
  currency: 'CHF',
  T: 3,
})

const advanced = reactive({ sigma: 20, r: 3, N: 20000, model: 'constant' })

function onUnderlyingSelect(ticker) {
  form.underlying_ticker = ticker
  const label = underlyingGroups.flatMap(g => g.items).find(it => it.ticker === ticker)?.label
  if (label) form.underlying_name = label
}

// ── Termes du produit (dynamiques, extraits du script sélectionné) ──
const parsedParams = ref([])
const paramOverrides = reactive({})
// Set only while duplicating an existing RFQ: the frozen snapshot overrides
// whatever form.template_type/script_id would otherwise resolve to, so a
// duplicate always reproduces the exact script that was actually quoted.
const duplicateSourceScript = ref(null)

function currentScriptText() {
  if (duplicateSourceScript.value) return duplicateSourceScript.value
  if (form.source === 'template') return examples[form.template_type] || ''
  return scripts.value.find(x => x.id === form.script_id)?.script_text || ''
}

async function refreshParsedParams(overrideValues = null) {
  const script = currentScriptText()
  Object.keys(paramOverrides).forEach(k => delete paramOverrides[k])
  if (!script.trim()) { parsedParams.value = []; return }
  try {
    const res = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
    })
    const data = await res.json()
    parsedParams.value = data.ok ? data.params : []
    for (const p of parsedParams.value) {
      const ov = overrideValues && (p.name in overrideValues) ? overrideValues[p.name] : null
      paramOverrides[p.name] = ov !== null ? (p.is_pct ? ov * 100 : ov) : p.raw_default
    }
  } catch {
    parsedParams.value = []
  }
}

function onSourceToggle(src) {
  form.source = src
  duplicateSourceScript.value = null
  refreshParsedParams()
}
function onTemplateChange() {
  duplicateSourceScript.value = null
  refreshParsedParams()
}
function onScriptChange() {
  duplicateSourceScript.value = null
  refreshParsedParams()
}

// ── Nominal formatting (séparateur de milliers, mirror de DealTab.vue) ──
const nominalRaw = ref('1 000 000')
const nominalValue = computed(() => {
  return parseFloat(nominalRaw.value.replace(/\s/g, '').replace(',', '.')) || 0
})
function formatNominal() {
  const n = nominalValue.value
  if (n) nominalRaw.value = n.toLocaleString('fr-FR').replace(/,/g, ' ')
}
function unformatNominal() {
  nominalRaw.value = String(nominalValue.value || '')
}
formatNominal()

const quoteForm = reactive({ provider: '', customProvider: '', contact: '' })

onMounted(async () => {
  loadingList.value = true
  try {
    await Promise.all([rfq.fetchList(), rfq.fetchProviders(), fetchScripts()])
  } finally {
    loadingList.value = false
  }
})

async function fetchScripts() {
  const res = await apiFetch('/api/db/scripts')
  if (res.ok) scripts.value = await res.json()
}

function openCreateForm() {
  showCreateForm.value = true
  selectedId.value = null
  rfq.current = null
  createError.value = ''
  duplicateSourceScript.value = null
  Object.assign(form, {
    name: '', ao_date: todayIso(), source: 'template', template_type: '', script_id: null,
    underlying_name: 'Sous-jacent', underlying_ticker: '', currency: 'CHF', T: 3,
  })
  Object.assign(advanced, { sigma: 20, r: 3, N: 20000, model: 'constant' })
  nominalRaw.value = '1 000 000'
  parsedParams.value = []
}

// Pre-fills the create form from an existing RFQ (new tender round on the
// same product, params free to adjust before submitting as a new RFQ).
async function duplicateRfq(source) {
  showCreateForm.value = true
  selectedId.value = null
  createError.value = ''
  const p = source.params || {}
  const u = (p.underlyings && p.underlyings[0]) || {}
  Object.assign(form, {
    name: `${source.name || source.reference} (copie)`,
    ao_date: todayIso(),
    source: source.script_id ? 'script' : 'template',
    template_type: source.template_type || '',
    script_id: source.script_id || null,
    underlying_name: u.name || 'Sous-jacent',
    underlying_ticker: u.ticker || '',
    currency: p.currency || 'CHF',
    T: p.T ?? 3,
  })
  Object.assign(advanced, {
    sigma: Math.round((u.sigma ?? 0.20) * 1000) / 10,
    r: Math.round((p.r ?? 0.03) * 1000) / 10,
    N: p.N ?? 20000,
    model: p.model || 'constant',
  })
  nominalRaw.value = String(p.notional ?? 1000000)
  formatNominal()
  duplicateSourceScript.value = source.script_snapshot
  await refreshParsedParams(p.user_params || {})
}

async function selectRfq(id) {
  showCreateForm.value = false
  selectedId.value = id
  computeError.value = ''
  await rfq.fetchOne(id)
  await refreshDetailParams()
}

const detailParsedParams = ref([])

async function refreshDetailParams() {
  const script = rfq.current?.script_snapshot || ''
  if (!script.trim()) { detailParsedParams.value = []; return }
  try {
    const res = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
    })
    const data = await res.json()
    detailParsedParams.value = data.ok ? data.params : []
  } catch {
    detailParsedParams.value = []
  }
}

const underlyingSummary = computed(() => (rfq.current?.params?.underlyings || [])[0] || {})

function fmtNominal(v) {
  return v === null || v === undefined ? '—' : Math.round(v).toLocaleString('fr-FR').replace(/,/g, ' ')
}

function fmtParamValue(p) {
  const raw = rfq.current?.params?.user_params?.[p.name]
  const v = raw ?? (p.is_pct ? p.raw_default / 100 : p.raw_default)
  return p.is_pct ? `${(v * 100).toFixed(2)}%` : v
}

async function submitCreate() {
  createError.value = ''
  if (!form.name.trim()) { createError.value = 'Le nom est requis'; return }
  if (form.source === 'template' && !form.template_type && !duplicateSourceScript.value) {
    createError.value = 'Choisissez un template'; return
  }
  if (form.source === 'script' && !form.script_id && !duplicateSourceScript.value) {
    createError.value = 'Choisissez un script'; return
  }
  const script_snapshot = currentScriptText()

  const user_params = {}
  for (const p of parsedParams.value) {
    const v = paramOverrides[p.name] ?? p.raw_default
    user_params[p.name] = p.is_pct ? v / 100 : v
  }

  creating.value = true
  try {
    const rfqObj = await rfq.create({
      name: form.name,
      ao_date: form.ao_date,
      template_type: form.source === 'template' ? form.template_type : '',
      script_id: form.source === 'script' ? form.script_id : null,
      script_snapshot,
      params: {
        underlyings: [{
          name: form.underlying_name, ticker: form.underlying_ticker,
          ccy: form.currency, sigma: advanced.sigma / 100, q: 0,
        }],
        corr_matrix: [[1]],
        r: advanced.r / 100, T: form.T, N: advanced.N, model: advanced.model,
        user_params,
        notional: nominalValue.value, currency: form.currency,
      },
    })
    showCreateForm.value = false
    await selectRfq(rfqObj.id)
    toasts.success('RFQ créée')
  } catch (e) {
    createError.value = e.message
  } finally {
    creating.value = false
  }
}

async function deleteRfq(id) {
  if (!confirm('Supprimer cette RFQ ?')) return
  await rfq.remove(id)
  if (selectedId.value === id) selectedId.value = null
  toasts.success('RFQ supprimée')
}

async function computeModelPrice() {
  computing.value = true
  computeError.value = ''
  try {
    await rfq.computeModelPrice(rfq.current)
  } catch (e) {
    computeError.value = e.message
  } finally {
    computing.value = false
  }
}

function openAddQuote() {
  quoteForm.provider = rfq.providers[0]?.label || 'autre'
  quoteForm.customProvider = ''
  quoteForm.contact = ''
  addingQuote.value = true
}

async function submitAddQuote() {
  const provider = quoteForm.provider === 'autre' ? (quoteForm.customProvider.trim() || 'Autre') : quoteForm.provider
  await rfq.addQuote(rfq.current.id, { provider, contact: quoteForm.contact || null })
  addingQuote.value = false
}

async function removeQuote(quoteId) {
  await rfq.removeQuote(rfq.current.id, quoteId)
}

function updateQuoteField(q, field, value) {
  rfq.updateQuote(rfq.current.id, q.id, { [field]: value })
}

function onQuotePriceChange(q, value) {
  const price = value === '' ? null : Number(value)
  const payload = { price }
  // First time a price is entered, log the response as received now unless
  // a date was already set explicitly.
  if (price !== null && !q.quoted_at) payload.quoted_at = new Date().toISOString()
  rfq.updateQuote(rfq.current.id, q.id, payload)
}

function onQuoteDateChange(q, value) {
  rfq.updateQuote(rfq.current.id, q.id, { quoted_at: value ? new Date(value).toISOString() : null })
}

// <input type="datetime-local"> expects "YYYY-MM-DDTHH:mm" in local time.
function toDatetimeLocal(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Plain "YYYY-MM-DD" strings (ao_date) are reformatted directly, never
// through Date(), which would parse them as UTC midnight and can shift the
// displayed day by one in negative-offset timezones.
function fmtDateOnly(iso) {
  if (!iso) return '—'
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}.${m[2]}.${m[1]}` : new Date(iso).toLocaleDateString('fr-FR')
}

function providerLabel(id) {
  return rfq.providers.find(p => p.id === id)?.label || id
}

function fmtPrice(v) {
  return v === null || v === undefined ? '—' : `${v.toFixed(2)}%`
}

function fmtDate(iso) {
  return new Date(iso).toLocaleString('fr-FR')
}

function spreadBps(q) {
  const model = rfq.current?.model_price
  if (q.price === null || q.price === undefined || model === null || model === undefined) return '—'
  return `${Math.round((q.price - model) / model * 10000)} bps`
}

function spreadClass(q) {
  const model = rfq.current?.model_price
  if (q.price === null || q.price === undefined || model === null || model === undefined) return 'text-slate-600'
  return q.price >= model ? 'text-green-400' : 'text-red-400'
}

const STATUS_LABELS = { draft: 'Brouillon', envoye: 'Envoyée', quote: 'Cotée', clos: 'Clôturée' }
const STATUS_BADGES = {
  draft:  'bg-slate-800 text-slate-400 border-slate-700',
  envoye: 'bg-blue-900/50 text-blue-300 border-blue-800',
  quote:  'bg-green-900/50 text-green-400 border-green-800',
  clos:   'bg-slate-800 text-slate-500 border-slate-700',
}
function statusLabel(s) { return STATUS_LABELS[s] || s }
function statusBadge(s) { return STATUS_BADGES[s] || STATUS_BADGES.draft }
</script>
