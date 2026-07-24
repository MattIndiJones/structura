<template>
  <div class="flex flex-col gap-4">

    <!-- Toolbar -->
    <div class="flex items-center gap-2 flex-wrap">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mr-auto">PayScript</h2>

      <!-- Normal / Expert toggle -->
      <div class="flex items-center text-[10px] border border-slate-700 rounded overflow-hidden shrink-0">
        <button
          :class="['px-2 py-1 transition-colors', !expertMode ? 'bg-slate-700 text-slate-200 font-semibold' : 'text-slate-500 hover:text-slate-400']"
          @click="expertMode = false"
        >Normal</button>
        <button
          :class="['px-2 py-1 transition-colors', expertMode ? 'bg-blue-900/80 text-blue-300 font-semibold' : 'text-slate-500 hover:text-slate-400']"
          @click="expertMode = true"
        >Expert</button>
      </div>
      <HelpTip width="w-72" text="Normal : dates AT écrites en dur (AT 1, 2, 3). Expert : calendrier CONSTAT() généré (start/end/roll/fréquence/stub), pratique pour des échéanciers réguliers longs sans lister chaque date à la main, et pour rejouer un calendrier réel avec jours fériés/roll gérés proprement. Change seulement les templates chargés — ne convertit pas le script actuellement en cours d'édition." />

      <select class="select text-xs w-auto" @change="loadExample($event.target.value); $event.target.value=''">
        <option value="">{{ expertMode ? 'Exemples (expert)…' : 'Exemples…' }}</option>
        <optgroup v-for="(items, group) in groupedTemplates" :key="group" :label="group">
          <option v-for="t in items" :key="t.key" :value="t.key">{{ t.label }}</option>
        </optgroup>
      </select>

      <!-- Script name chip (when loaded from DB) -->
      <span v-if="store.currentScriptName"
            class="text-[10px] text-slate-500 border border-slate-700 rounded px-1.5 py-0.5 truncate max-w-[140px]"
            :title="store.currentScriptName">
        {{ store.currentScriptName }}
      </span>

      <!-- Save / Update button -->
      <button v-if="store.currentScriptId"
              class="btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5 shrink-0"
              :disabled="saving"
              @click="quickSave">
        <span v-if="saving" class="w-3 h-3 border border-white/60 border-t-transparent rounded-full animate-spin"></span>
        {{ saving ? '…' : 'Enregistrer' }}
      </button>
      <button v-else
              class="btn-primary text-xs px-3 py-1.5 shrink-0"
              @click="openSaveModal">
        Sauvegarder
      </button>
    </div>

    <!-- Save modal -->
    <BaseModal v-model="saveModal.open" title="Sauvegarder le script" max-width="420px">
      <div class="flex flex-col gap-4">
        <AlertMessage v-if="saveModal.error" kind="error">{{ saveModal.error }}</AlertMessage>

        <div class="flex flex-col gap-1">
          <label class="label">Nom *</label>
          <input ref="saveNameInput" v-model="saveModal.name" type="text" class="input"
                 placeholder="Mon autocall 3Y…"
                 @keyup.enter="doSave" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Description</label>
          <input v-model="saveModal.description" type="text" class="input"
                 placeholder="Description courte (optionnel)" />
        </div>
        <div class="flex flex-col gap-1">
          <label class="label">Tags</label>
          <input v-model="saveModal.tags" type="text" class="input"
                 placeholder="autocall, 3Y, EUR…" />
        </div>
        <label class="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
          <input type="checkbox" v-model="saveModal.isShared" class="accent-blue-500" />
          Partager avec mon entité
        </label>
      </div>
      <template #footer>
        <button class="btn-secondary text-xs" @click="saveModal.open = false">Annuler</button>
        <button class="btn-primary text-xs flex items-center gap-1.5" :disabled="saving" @click="doSave">
          <span v-if="saving" class="w-3 h-3 border border-white/60 border-t-transparent rounded-full animate-spin"></span>
          Sauvegarder
        </button>
      </template>
    </BaseModal>

    <!-- Editor -->
    <div class="card p-0 overflow-hidden">
      <SensitiveValue mode="blur">
        <textarea
          v-model="store.script"
          class="code-editor w-full"
          spellcheck="false"
          placeholder="# Écrivez votre PayScript ici…"
          @input="onInput"
          @keydown.tab.prevent="insertTab"
          style="min-height:340px"
        />
      </SensitiveValue>
    </div>

    <!-- Parse error -->
    <div v-if="store.parseError"
         class="bg-red-950/60 border border-red-800 rounded-lg p-3 text-xs text-red-300 font-mono whitespace-pre-wrap">
      <span class="font-bold text-red-400">Erreur PayScript :</span>
      {{ Array.isArray(store.parseError) ? store.parseError.join('\n') : store.parseError }}
    </div>

    <!-- Dynamic PARAM inputs -->
    <div v-if="store.scriptParams.length > 0" class="card">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Paramètres du script
        <HelpTip text="Détectés automatiquement depuis les lignes PARAM du script (parsing à chaque modification). Les valeurs saisies ici surchargent les valeurs par défaut du script pour le pricing courant, sans modifier le texte du script lui-même." />
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div v-for="p in store.scriptParams" :key="p.name" class="flex flex-col gap-1"
          :class="p.kind === 'array' ? 'col-span-2 sm:col-span-1' : ''">
          <label class="label">{{ p.name }}
            <span v-if="p.kind === 'array'" class="text-slate-600 font-normal normal-case">
              (par observation)
              <HelpTip text="Une valeur par observation, dans l'ordre des dates AT. La dernière ligne s'étend aux observations suivantes — une seule ligne = valeur constante. Une ligne en trop est ignorée." />
            </span>
          </label>

          <!-- PARAM() : une ligne par observation -->
          <template v-if="p.kind === 'array'">
            <div v-for="(v, ri) in store.paramOverrides[p.name]" :key="ri"
              class="flex items-center gap-1.5">
              <span class="text-[10px] text-slate-600 font-mono w-9 shrink-0">Obs {{ ri + 1 }}</span>
              <SensitiveValue mode="input">
                <div class="relative flex-1">
                  <input type="number" class="input pr-7 text-xs py-1" step="any"
                    v-model.number="store.paramOverrides[p.name][ri]" />
                  <span v-if="p.is_pct" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-500">%</span>
                </div>
              </SensitiveValue>
              <button v-if="store.paramOverrides[p.name].length > 1"
                class="text-slate-600 hover:text-red-400 text-xs shrink-0"
                @click="store.paramOverrides[p.name].splice(ri, 1)">✕</button>
            </div>
            <button class="text-xs text-blue-400 hover:underline self-start"
              @click="store.paramOverrides[p.name].push(store.paramOverrides[p.name].at(-1) ?? p.display_default)">
              + Ajouter une observation
            </button>
          </template>

          <!-- PARAM scalaire -->
          <SensitiveValue v-else mode="input">
            <div class="relative">
              <input
                :id="`param-${p.name}`"
                type="number"
                class="input pr-7"
                v-model.number="store.paramOverrides[p.name]"
                step="any"
              />
              <span v-if="p.is_pct" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-500">%</span>
            </div>
          </SensitiveValue>
          <span v-if="p.desc && p.desc !== p.name" class="text-xs text-slate-600">{{ p.desc }}</span>
        </div>
      </div>
    </div>

    <!-- Rappel calendrier (mode expert — CONSTAT) — édition dans l'onglet Deal -->
    <div v-if="store.scriptConstats.length > 0" class="card">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Calendrier du script (CONSTAT)
        <HelpTip width="w-72" text="Les dates concrètes (début/fin/roll/fréquence) de chaque calendrier référencé ici se saisissent dans l'onglet Deal, à côté de l'aperçu des constatations — pas dans le script lui-même." />
      </div>
      <div class="flex flex-wrap gap-2">
        <span v-for="c in store.scriptConstats" :key="c.name"
          class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono border"
          :class="isConstatResolved(c) ? 'border-slate-700 text-slate-400' : 'border-amber-800/60 text-amber-400'">
          {{ c.name }}
          <span v-if="isConstatResolved(c)" class="text-emerald-500">✓</span>
          <span v-else>⚠ non défini</span>
        </span>
      </div>
      <p class="text-[10px] text-slate-600 mt-2">→ défini dans l'onglet Deal</p>
    </div>

    <!-- PayScript quick reference -->
    <details class="card text-xs text-slate-400">
      <summary class="font-bold cursor-pointer text-slate-300 select-none">▸ Référence PayScript</summary>
      <div v-for="sec in referenceSections" :key="sec.title" class="mt-3">
        <div class="text-slate-500 font-semibold uppercase tracking-wide text-[10px] mb-1.5">{{ sec.title }}</div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 font-mono">
          <div v-for="r in sec.items" :key="r.kw">
            <span class="text-purple-400 font-bold">{{ r.kw }}</span>
            <span class="text-slate-500 ml-2">{{ r.desc }}</span>
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useToastsStore } from '../stores/toasts.js'
import SensitiveValue from './SensitiveValue.vue'
import HelpTip from './HelpTip.vue'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'
import { templateMeta, examples, expertExamples } from '../data/payscriptTemplates.js'

const store = usePricingStore()
const toasts = useToastsStore()

const groupedTemplates = computed(() => {
  const groups = {}
  for (const t of templateMeta) {
    (groups[t.group] ||= []).push(t)
  }
  return groups
})
let debounceTimer = null

const expertMode = ref(false)

// ── Save / update ──────────────────────────────────────────────────
const saving       = ref(false)
const saveNameInput = ref(null)
const saveModal = reactive({ open: false, name: '', description: '', tags: '', isShared: false, error: '' })

function openSaveModal() {
  saveModal.name        = store.currentScriptName || ''
  saveModal.description = ''
  saveModal.tags        = ''
  saveModal.isShared    = false
  saveModal.error       = ''
  saveModal.open        = true
  nextTick(() => saveNameInput.value?.focus())
}

async function quickSave() {
  saving.value = true
  try {
    await store.updateScript()
    toasts.success('Script mis à jour')
  } catch (e) {
    openSaveModal()
    saveModal.error = e.message
  } finally {
    saving.value = false
  }
}

async function doSave() {
  const name = saveModal.name.trim()
  if (!name) { saveModal.error = 'Le nom est requis'; return }
  saving.value = true
  saveModal.error = ''
  try {
    await store.saveScript({
      name,
      description: saveModal.description,
      tags: saveModal.tags,
      isShared: saveModal.isShared,
    })
    saveModal.open = false
    toasts.success('Script sauvegardé')
  } catch (e) {
    saveModal.error = e.message
  } finally {
    saving.value = false
  }
}

function isConstatResolved(c) {
  const v = store.constatOverrides[c.name]
  if (!v) return false
  if (c.kind === 'single') return !!v
  return !!(v.start_date && v.end_date)
}

// ── Date helpers ───────────────────────────────────────────────────
function isoToday() {
  return new Date().toISOString().slice(0, 10)
}

function addYears(n) {
  const d = new Date()
  d.setFullYear(d.getFullYear() + n)
  return d.toISOString().slice(0, 10)
}

function addMonths(n) {
  const d = new Date()
  d.setMonth(d.getMonth() + n)
  return d.toISOString().slice(0, 10)
}

// Templates (examples / expertExamples) now live in ../data/payscriptTemplates.js
// ── Expert CONSTAT pre-fill (dates computed from today) ────────────
function getExpertConstatDefaults(key) {
  const t0 = isoToday()
  const defs = []

  // Products with CONSTAT() OBSERVATIONS (annual schedule)
  const scheduleMap = {
    autocall_athena:            3,
    autocall_phoenix:           3,
    autocall_worst_of:          3,
    autocall_gear_put:          3,
    autocall_gear_put_worst_of: 3,
  }

  // Products with CONSTAT MATURITE (single date) → years to maturity
  const singleMap = {
    call_vanilla:        1,
    put_vanilla:         1,
    call_spread:         1,
    digital:             1,
    capital_garanti:     5,
    reverse_convertible: 1,
    twin_win:            3,
    booster:             3,
    zcb:                 1,
    shark_note:          3,
    shark_note_worst_of: 3,
  }

  // Products with CONSTAT() STRIKE_FIX (fixing window, always before OBSERVATIONS)
  const strikeFixMap = {
    autocall_gear_put:          1,
    autocall_gear_put_worst_of: 1,
  }

  if (key in scheduleMap) {
    const endDate = addYears(scheduleMap[key])
    defs.push({ name: 'OBSERVATIONS', kind: 'schedule', values: {
      start_date: t0, end_date: endDate, roll_date: endDate,
      frequency: { value: 1, unit: 'Y' }, stub: 'short_last',
    }})
  }

  if (key in singleMap) {
    defs.push({ name: 'MATURITE', kind: 'single', values: addYears(singleMap[key]) })
  }

  if (key in strikeFixMap) {
    const endDate = addMonths(strikeFixMap[key])
    defs.push({ name: 'STRIKE_FIX', kind: 'schedule', values: {
      start_date: t0, end_date: endDate, roll_date: endDate,
      frequency: { value: 1, unit: 'D' }, stub: 'short_last',
    }})
  }

  return defs
}

// ── Load example ───────────────────────────────────────────────────
async function loadExample(key) {
  if (!key) return
  Object.keys(store.paramOverrides).forEach(k => delete store.paramOverrides[k])

  if (expertMode.value) {
    store.script = expertExamples[key] || examples[key] || ''
    await store.parseScript()

    for (const def of getExpertConstatDefaults(key)) {
      if (!(def.name in store.constatOverrides)) continue
      if (def.kind === 'single') {
        store.constatOverrides[def.name] = def.values
      } else {
        const ov = store.constatOverrides[def.name]
        ov.start_date = def.values.start_date
        ov.end_date   = def.values.end_date
        ov.roll_date  = def.values.roll_date
        ov.frequency.value = def.values.frequency.value
        ov.frequency.unit  = def.values.frequency.unit
        ov.stub = def.values.stub
      }
    }
  } else {
    store.script = examples[key] || ''
    store.parseScript()
  }
}

// ── Misc ───────────────────────────────────────────────────────────
function onInput() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => store.parseScript(), 500)
}

function insertTab(e) {
  const ta = e.target, s = ta.selectionStart, end = ta.selectionEnd
  store.script = store.script.substring(0, s) + '  ' + store.script.substring(end)
  ta.selectionStart = ta.selectionEnd = s + 2
}

const referenceSections = [
  {
    title: 'Déclarations & dates',
    items: [
      { kw: 'PARAM K = 5%', desc: 'Paramètre modifiable par l\'UI ("desc" ou # desc optionnelle)' },
      { kw: 'PARAM() K = 5%', desc: 'Paramètre par observation : tableau d\'une valeur par date AT dans l\'UI (la dernière ligne s\'étend, une ligne = constant). Le = 5% pré-remplit la 1ère ligne' },
      { kw: 'PARAM M_XXX', desc: 'Préfixe M_ = surveillé par la watchlist Booking. Direction et observable déduits de l\'usage : WOF >= M_X = rappel par le haut, WOF < M_X = KI par le bas' },
      { kw: 'AT 1, 2, 3:', desc: 'Événement à des dates précises (années)' },
      { kw: 'AT 1..5:0.5', desc: 'Événement sur une plage (début..fin:pas, pas=1 par défaut)' },
      { kw: 'AT MATURITY:', desc: 'Événement à maturité' },
      { kw: 'CONSTAT Nom', desc: 'Date unique nommée, remplie via l\'UI (mode expert)' },
      { kw: 'CONSTAT() Nom', desc: 'Calendrier nommé : début/fin/roll/fréquence/stub, rempli via l\'UI' },
      { kw: 'CONSTAT()() Nom', desc: 'Comme CONSTAT() + une sous-fréquence (subdivise chaque intervalle)' },
      { kw: 'AT Nom:', desc: 'Événement à chaque date d\'un calendrier nommé' },
      { kw: 'AT Nom.first:', desc: 'Événement additionnel à la 1ère date du calendrier' },
      { kw: 'AT Nom.last:', desc: 'Événement additionnel à la dernière date (ex : check KI à maturité)' },
      { kw: 'AT Nom[3]:', desc: 'Événement additionnel à la 3e date (1-indexé)' },
      { kw: 'CONSTAT() STRIKE_FIX', desc: 'Nom réservé : fenêtre de fixing du strike (toujours avant le calendrier d\'autocall). Pas de bloc AT — utiliser FIX_MIN/FIX_MAX/FIX_AVG' },
    ],
  },
  {
    title: 'Instructions',
    items: [
      { kw: 'SET X = expr', desc: 'Stocker une valeur (variable mémo)' },
      { kw: 'PAY expr "label"', desc: 'Flux actualisé au pricing, étiquette optionnelle (alias : FLOW)' },
      { kw: 'ACCRUE expr', desc: 'Accumuler une valeur dans ACCUM' },
      { kw: 'IF cond: / ELSE IF: / ELSE:', desc: 'Branchement conditionnel' },
      { kw: 'STOP', desc: 'Arrêter le chemin (autocall)' },
    ],
  },
  {
    title: 'Variables intégrées',
    items: [
      { kw: 'WOF', desc: 'Worst-of actuel (min des spots)' },
      { kw: 'BOF', desc: 'Best-of actuel (max des spots)' },
      { kw: 'WOF_MIN', desc: 'Min historique du WoF depuis t=0' },
      { kw: 'BOF_MAX', desc: 'Max historique du BoF depuis t=0' },
      { kw: 'FIX_MIN / FIX_MAX / FIX_AVG', desc: 'Min/max/moyenne du WoF sur la fenêtre CONSTAT() STRIKE_FIX — niveau de référence (fixing), indépendant du strike du put. Ex: SET REF = FIX_AVG puis SET PERF = WOF/REF, et utiliser PERF (pas WOF) partout ensuite' },
      { kw: 'ACCUM', desc: 'Valeur accumulée via ACCRUE' },
      { kw: 'INDEX', desc: 'Numéro d\'observation (1, 2, …)' },
      { kw: 'T', desc: 'Temps actuel (en années)' },
      { kw: 'N', desc: 'Nombre de sous-jacents' },
      { kw: 'S[i]', desc: 'Spot du sous-jacent i (1-indexé)' },
      { kw: 'S_MIN[i] / S_MAX[i]', desc: 'Min/max historique du sous-jacent i' },
      { kw: 'S_PREV[i]', desc: 'Spot du sous-jacent i à l\'observation précédente' },
      { kw: 'REALVOL', desc: 'Vol réalisée annualisée du WoF depuis t=0' },
    ],
  },
  {
    title: 'Fonctions',
    items: [
      { kw: 'MAX(a, b) / MIN(a, b)', desc: 'Maximum / minimum' },
      { kw: 'ABS(x)', desc: 'Valeur absolue' },
      { kw: 'FLOOR(x) / CEIL(x)', desc: 'Arrondi inférieur / supérieur' },
      { kw: 'SQRT(x) / LOG(x) / EXP(x)', desc: 'Racine carrée, log népérien, exponentielle' },
      { kw: 'ROUND(x)', desc: 'Arrondi à l\'entier' },
      { kw: 'INDIC(cond)', desc: '1 si vrai, 0 sinon' },
      { kw: 'BASKET', desc: 'Moyenne simple des spots (équipondérée)' },
      { kw: 'BASKET(w1, w2, …)', desc: 'Panier pondéré des spots' },
    ],
  },
  {
    title: 'Opérateurs logiques & comparaisons',
    items: [
      { kw: 'AND / OR / NOT', desc: 'Et / ou / négation' },
      { kw: 'TRUE / FALSE', desc: 'Booléens' },
      { kw: '>=  <=  =  !=', desc: 'Comparateurs (= et == sont équivalents)' },
    ],
  },
]

store.parseScript()
</script>
