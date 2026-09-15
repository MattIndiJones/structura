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

      <select class="select text-xs w-auto" :disabled="store.contractTermsLocked"
              @change="loadExample($event.target.value); $event.target.value=''">
        <option value="">{{ expertMode ? 'Exemples (expert)…' : 'Exemples…' }}</option>
        <option value="__blank__">— Script libre (vide) —</option>
        <optgroup v-for="(items, group) in groupedTemplates" :key="group" :label="group">
          <option v-for="t in items" :key="t.key" :value="t.key">{{ t.label }}</option>
        </optgroup>
      </select>

      <button class="btn-secondary text-xs px-3 py-1.5 shrink-0"
              :disabled="store.contractTermsLocked" @click="assistantOpen = true">
        ✨ Assistant IA
      </button>
      <HelpTip width="w-72" text="Décrivez le produit en français, un modèle propose un script PayScript. Rien n'est appliqué automatiquement : le script arrive accompagné d'une reformulation en français et d'une fiche de contrôle, et c'est vous qui l'adoptez. Ollama tourne en local — la description ne quitte pas la machine." />

      <!-- Explicit validation: the same gesture as Ctrl+S (Cmd+S on a Mac). -->
      <button class="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5 shrink-0"
              :disabled="store.contractTermsLocked || validating"
              title="Valider le script (Ctrl+S) : ses déclarations s'appliquent à Economics"
              @click="validate">
        <span v-if="validating" class="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin"></span>
        Valider
      </button>

      <!-- Script name chip (when loaded from DB) -->
      <span v-if="store.currentScriptName"
            class="text-[10px] text-slate-500 border border-slate-700 rounded px-1.5 py-0.5 truncate max-w-[140px]"
            :title="store.currentScriptName">
        {{ store.currentScriptName }}
      </span>

      <!-- Save / Update button -->
      <button v-if="store.currentScriptId"
              class="btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5 shrink-0"
              :disabled="saving || store.contractTermsLocked"
              @click="quickSave">
        <span v-if="saving" class="w-3 h-3 border border-white/60 border-t-transparent rounded-full animate-spin"></span>
        {{ saving ? '…' : 'Enregistrer' }}
      </button>
      <button v-else
              class="btn-primary text-xs px-3 py-1.5 shrink-0"
              :disabled="store.contractTermsLocked"
              @click="openSaveModal">
        Sauvegarder
      </button>
    </div>

    <AlertMessage v-if="notice" kind="success" dismissible @dismiss="notice = ''">{{ notice }}</AlertMessage>
    <AlertMessage v-if="store.scriptDirty && !store.contractTermsLocked" kind="warning">
      Script modifié, non validé — Ctrl+S ou « Valider » applique ses déclarations à Economics.
    </AlertMessage>
    <AlertMessage v-else-if="validatedNotice && !store.contractTermsLocked" kind="success"
                  dismissible @dismiss="validatedNotice = false">
      Script validé.
    </AlertMessage>
    <AlertMessage v-if="reportLines.length" kind="info" dismissible @dismiss="store.validationReport = null">
      Valeurs mises à jour par le script à la validation :
      <span v-for="line in reportLines" :key="line" class="block font-mono text-[11px]">{{ line }}</span>
    </AlertMessage>

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
          :readonly="store.contractTermsLocked"
          :maxlength="store.calculationLimits.maxScriptChars"
          spellcheck="false"
          placeholder="# Écrivez votre PayScript ici…"
          @keydown.tab="onEditorTab"
          style="min-height:340px"
        />
      </SensitiveValue>
      <div class="px-3 py-1.5 border-t border-slate-800 text-[10px] font-mono text-right"
           :class="store.script.length > store.calculationLimits.maxScriptChars * 0.9
             ? 'text-amber-500' : 'text-slate-600'">
        {{ store.script.length.toLocaleString() }} / {{ store.calculationLimits.maxScriptChars.toLocaleString() }} caractères ·
        {{ store.script.split('\n').length.toLocaleString() }} / {{ store.calculationLimits.maxScriptLines.toLocaleString() }} lignes
      </div>
    </div>

    <!-- Parse error -->
    <div v-if="store.parseError"
         class="bg-red-950/60 border border-red-800 rounded-lg p-3 text-xs text-red-300 font-mono whitespace-pre-wrap">
      <span class="font-bold text-red-400">Erreur PayScript{{ store.scriptDirty ? ' (dernière validation)' : '' }} :</span>
      {{ Array.isArray(store.parseError) ? store.parseError.join('\n') : store.parseError }}
    </div>

    <!-- Les déclarations restent visibles ici, mais leur valeur n'a qu'un
         seul lieu d'édition : Economics. Deux contrôles reliés à la même
         surcharge rendaient ambiguë la valeur réellement utilisée. -->
    <div v-if="store.scriptParams.length || store.scriptConstats.length" class="card">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Déclarations économiques</div>
          <div class="flex flex-wrap gap-1.5 mt-2">
            <span v-for="p in store.scriptParams" :key="p.name" class="badge badge-muted font-mono">
              {{ p.kind === 'array' ? 'PARAM()' : 'PARAM' }} {{ p.name }}
            </span>
            <span v-for="c in store.scriptConstats" :key="c.name" class="badge badge-muted font-mono">
              CONSTAT {{ c.name }}
            </span>
          </div>
          <p class="text-[10px] text-slate-600 mt-2">
            Le script déclare les termes ; leurs valeurs et échéanciers sont pilotés dans Economics.
          </p>
        </div>
        <button class="btn-secondary text-xs shrink-0" @click="store.leftTab = 'economics'">
          Ouvrir Economics
        </button>
      </div>
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

    <ScriptAssistantModal v-model="assistantOpen"
                          @adopted="notice = 'Script adopté depuis l\'assistant — relisez-le avant de pricer.'" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import SensitiveValue from './SensitiveValue.vue'
import HelpTip from './HelpTip.vue'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'
import ScriptAssistantModal from './ScriptAssistantModal.vue'
import { templateMeta, examples, expertExamples } from '../data/payscriptTemplates.js'

const store = usePricingStore()
const notice = ref('')

const groupedTemplates = computed(() => {
  const groups = {}
  for (const t of templateMeta) {
    // Un modèle `expertOnly` constate sur une période : sa fenêtre vit dans un
    // CONSTAT, que le mode normal ne déclare pas. Le proposer là chargerait un
    // script vide.
    if (t.expertOnly && !expertMode.value) continue
    ;(groups[t.group] ||= []).push(t)
  }
  return groups
})

const expertMode = ref(false)
const assistantOpen = ref(false)

// ── Validation (Ctrl+S / « Valider ») ─────────────────────────────
// Validating never saves: saving stays on the button at the top right.
const validating = ref(false)
const validatedNotice = ref(false)

async function validate() {
  if (store.contractTermsLocked || validating.value) return
  validating.value = true
  validatedNotice.value = false
  try {
    validatedNotice.value = await store.validateScript()
  } finally {
    validating.value = false
  }
}

// Intercepted anywhere in the Pricer, not only in the text area: a Ctrl+S
// typed from Economics used to open the browser's "Save page" dialog.
function onShortcut(event) {
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return
  if (String(event.key).toLowerCase() !== 's') return
  event.preventDefault()
  validate()
}

onMounted(() => window.addEventListener('keydown', onShortcut))
onBeforeUnmount(() => window.removeEventListener('keydown', onShortcut))

watch(() => store.scriptDirty, dirty => { if (dirty) validatedNotice.value = false })

function formatDeclared(value, isPct) {
  if (value === '' || value == null || Number.isNaN(Number(value))) return '—'
  const text = Number(value).toLocaleString('fr-FR', { maximumFractionDigits: 6 })
  return isPct ? `${text} %` : text
}

const reportLines = computed(() => {
  const report = store.validationReport
  if (!report) return []
  return [
    ...report.replaced.map(item =>
      `${item.name} : ${formatDeclared(item.before, item.beforePct)} → ${formatDeclared(item.after, item.afterPct)}`),
    ...report.keptRows.map(item =>
      `${item.name} : ${item.count} ligne(s) saisie(s) conservée(s)`
      + (item.unitChanged ? ' — unité changée, à vérifier' : '')),
  ]
})

// ── Save / update ──────────────────────────────────────────────────
const saving       = ref(false)
const saveNameInput = ref(null)
const saveModal = reactive({ open: false, name: '', description: '', tags: '', isShared: false, error: '' })

function openSaveModal() {
  if (store.contractTermsLocked) return
  saveModal.name        = store.currentScriptName || ''
  saveModal.description = ''
  saveModal.tags        = ''
  saveModal.isShared    = false
  saveModal.error       = ''
  notice.value          = ''
  saveModal.open        = true
  nextTick(() => saveNameInput.value?.focus())
}

async function quickSave() {
  if (store.contractTermsLocked) return
  saving.value = true
  notice.value = ''
  try {
    await store.updateScript()
    notice.value = 'Script mis à jour'
  } catch (e) {
    openSaveModal()
    saveModal.error = e.message
  } finally {
    saving.value = false
  }
}

async function doSave() {
  if (store.contractTermsLocked) return
  const name = saveModal.name.trim()
  if (!name) { saveModal.error = 'Le nom est requis'; return }
  saving.value = true
  saveModal.error = ''
  notice.value = ''
  try {
    await store.saveScript({
      name,
      description: saveModal.description,
      tags: saveModal.tags,
      isShared: saveModal.isShared,
    })
    saveModal.open = false
    notice.value = 'Script sauvegardé'
  } catch (e) {
    saveModal.error = e.message
  } finally {
    saving.value = false
  }
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
    call_moyenne:        1,
    call_lookback:       1,
  }

  // Produits portant une fenêtre de départ (STRIKE_FIX). La valeur est la
  // longueur par défaut de la fenêtre, en jours ouvrés — elle se re-saisit à
  // l'écran, c'est une donnée de term sheet.
  const strikeFixMap = {
    autocall_gear_put:          10,
    autocall_gear_put_worst_of: 10,
    call_moyenne:               10,
    call_lookback:              10,
  }
  // Constatation finale sur période : longueur par défaut, même unité.
  const finalWindowMap = { call_moyenne: 30 }

  // Calendrier à fenêtre de PÉRIODE : la sous-fréquence de relevé remplace la
  // longueur, qui n'a pas de sens quand la fenêtre est la période elle-même.
  const periodMap = { autocall_moyenne_periode: { years: 3, sample: { value: 3, unit: 'M' } } }
  if (key in periodMap) {
    const endDate = addYears(periodMap[key].years)
    defs.push({ name: 'OBSERVATIONS', kind: 'schedule', values: {
      start_date: t0, end_date: endDate, roll_date: endDate,
      frequency: { value: 1, unit: 'Y' }, stub: 'short_last',
      window_frequency: periodMap[key].sample,
    }})
    return defs
  }

  if (key in scheduleMap) {
    const endDate = addYears(scheduleMap[key])
    defs.push({ name: 'OBSERVATIONS', kind: 'schedule', values: {
      start_date: t0, end_date: endDate, roll_date: endDate,
      frequency: { value: 1, unit: 'Y' }, stub: 'short_last',
    }})
  }

  if (key in singleMap) {
    const win = finalWindowMap[key]
    defs.push({ name: 'MATURITE', kind: 'single',
                values: win
                  ? { date: addYears(singleMap[key]),
                      window_length: { value: win, unit: 'D' },
                      window_frequency: { value: 1, unit: 'D' } }
                  : addYears(singleMap[key]) })
  }

  if (key in strikeFixMap) {
    defs.push({ name: 'STRIKE_FIX', kind: 'single', values: {
      date: t0,
      window_length: { value: strikeFixMap[key], unit: 'D' },
      window_frequency: { value: 1, unit: 'D' },
    }})
  }

  return defs
}

// ── Load example ───────────────────────────────────────────────────
const BLANK_SCRIPT = `# Script libre — décrivez votre payoff.
# Aide : bouton ✨ Assistant IA, ou le mémo de vocabulaire ci-dessous.

AT MATURITY:
  PAY 1
`

async function loadExample(key) {
  if (!key || store.contractTermsLocked) return
  Object.keys(store.paramOverrides).forEach(k => delete store.paramOverrides[k])

  // Point de départ vierge : un squelette qui parse (donc qui price) plutôt
  // qu'un éditeur vide, qui afficherait une erreur avant la première frappe.
  if (key === '__blank__') {
    store.script = BLANK_SCRIPT
    await store.parseScript()
    return
  }

  if (expertMode.value) {
    store.script = expertExamples[key] || examples[key] || ''
    await store.parseScript()
    applyConstatDefaults(key)
  } else {
    store.script = examples[key] || ''
    await store.parseScript()
    applyConstatDefaults(key)
  }
}

/** Pré-remplit les CONSTAT déclarés par le modèle qu'on vient de charger. */
function applyConstatDefaults(key) {
  for (const def of getExpertConstatDefaults(key)) {
    if (!(def.name in store.constatOverrides)) continue
    const ov = store.constatOverrides[def.name]
    if (def.kind === 'single') {
      // Un modèle à fenêtre stocke un objet : on le remplit plutôt que de
      // l'écraser, sinon la réactivité du panneau saute.
      if (typeof def.values === 'object' && ov && typeof ov === 'object') {
        ov.date = def.values.date
        _applyTenor(ov, 'window_length', def.values.window_length)
        _applyTenor(ov, 'window_frequency', def.values.window_frequency)
      } else {
        store.constatOverrides[def.name] = def.values
      }
    } else if (ov && typeof ov === 'object') {
      ov.start_date = def.values.start_date
      ov.end_date   = def.values.end_date
      ov.roll_date  = def.values.roll_date
      ov.frequency.value = def.values.frequency.value
      ov.frequency.unit  = def.values.frequency.unit
      ov.stub = def.values.stub
    }
  }
}

function _applyTenor(ov, key, tenor) {
  if (!tenor) return
  if (!ov[key]) ov[key] = { value: tenor.value, unit: tenor.unit }
  else { ov[key].value = tenor.value; ov[key].unit = tenor.unit }
}

// ── Misc ───────────────────────────────────────────────────────────
function onEditorTab(event) {
  if (store.contractTermsLocked) return
  event.preventDefault()
  insertTab(event)
}

function insertTab(e) {
  const ta = e.target, s = ta.selectionStart, end = ta.selectionEnd
  store.script = store.script.substring(0, s) + '  ' + store.script.substring(end)
  ta.selectionStart = ta.selectionEnd = s + 2
}

// Entries are listed in alphabetical order within each section (sections keep
// their reading order). Insert a new entry at its alphabetical place.
const referenceSections = [
  {
    title: 'Déclarations & dates',
    items: [
      { kw: 'AT 1, 2, 3:', desc: 'Événement à des dates précises, en années depuis la date de strike' },
      { kw: 'AT 1..5:0.5', desc: 'Événement sur une plage (début..fin:pas, pas=1 par défaut)' },
      { kw: 'AT MATURITY:', desc: 'Événement à maturité' },
      { kw: 'AT Nom:', desc: 'Événement à chaque date d\'un calendrier nommé' },
      { kw: 'AT Nom.first:', desc: 'Événement additionnel à la 1ère date du calendrier' },
      { kw: 'AT Nom.last:', desc: 'Événement additionnel à la dernière date (ex : check KI à maturité)' },
      { kw: 'AT Nom.last.last:', desc: 'Deux niveaux de qualificateur : le premier désigne une constatation, le second UN RELEVÉ dans sa fenêtre. .last = la dernière constatation (donc la moyenne), .last.last = son dernier relevé (donc le cours). C\'est ainsi qu\'un PDI sur clôture cohabite avec un coupon sur moyenne, même date, même calendrier' },
      { kw: 'AT Nom[3]:', desc: 'Événement additionnel à la 3e date (1-indexé)' },
      { kw: 'CONSTAT Nom', desc: 'Date unique nommée, remplie via l\'UI (mode expert)' },
      { kw: 'CONSTAT Nom MIN|MAX|AVG', desc: 'Constatation sur PERIODE : chaque date devient le min/max/moyenne des cours de CHAQUE sous-jacent sur une fenetre, et WOF/BOF/BASKET n\'agregent qu\'ensuite. Longueur et frequence de la fenetre se saisissent a l\'ecran : ce sont des donnees de term sheet, pas du payoff' },
      { kw: 'CONSTAT STRIKE_FIX AVG', desc: 'Nom reserve : la fenetre de depart, celle qui fixe S0 par sous-jacent. Elle PART de sa date vers l\'avant, la ou toute autre fenetre arrive a la sienne. Ensuite WOF/BOF/BASKET valent directement la performance contre S0. Tant qu\'elle n\'est pas close, les barrieres americaines (WOF_MIN) ne courent pas' },
      { kw: 'CONSTAT() Nom', desc: 'Calendrier nommé : début/fin/roll/fréquence/stub, rempli via l\'UI' },
      { kw: 'CONSTAT() Nom AVG PERIOD', desc: 'Fenêtre = LA PÉRIODE, d\'une constatation à la suivante, échantillonnée à la fréquence de relevé saisie à l\'écran. Trois constatations annuelles moyennées sur leurs relevés trimestriels, par exemple. Sans PERIOD, la fenêtre a une longueur fixe avant chaque date' },
      { kw: 'CONSTAT()() Nom', desc: 'Comme CONSTAT() + une sous-fréquence (subdivise chaque intervalle)' },
      { kw: 'Ctrl+S / Valider', desc: 'Valide le script : une valeur initiale ou une unité modifiée s\'applique à Economics. N\'enregistre pas' },
      { kw: 'PARAM K = 5%', desc: 'Paramètre modifiable par l\'UI ("desc" ou # desc optionnelle)' },
      { kw: 'PARAM M_XXX', desc: 'Préfixe M_ = surveillé par la watchlist Booking. Direction et observable déduits de l\'usage : WOF >= M_X = rappel par le haut, WOF < M_X = KI par le bas' },
      { kw: 'PARAM() K = 5%', desc: 'Paramètre par observation : tableau d\'une valeur par date AT dans l\'UI (la dernière ligne s\'étend, une ligne = constant). Valeur obligatoire, comme pour PARAM : le = 5% pré-remplit la 1ère ligne' },
    ],
  },
  {
    title: 'Instructions',
    items: [
      { kw: 'ACCRUE expr', desc: 'Accumuler une valeur dans ACCUM' },
      { kw: 'IF cond: / ELSE IF: / ELSE:', desc: 'Branchement conditionnel' },
      { kw: 'PAY expr "label"', desc: 'Flux actualisé au pricing, étiquette optionnelle (alias : FLOW)' },
      { kw: 'SET X = expr', desc: 'Stocker une valeur (variable mémo)' },
      { kw: 'STOP', desc: 'Arrêter le chemin (autocall)' },
    ],
  },
  {
    title: 'Variables intégrées',
    items: [
      { kw: 'ACCUM', desc: 'Valeur accumulée via ACCRUE' },
      { kw: 'BOF', desc: 'Best-of actuel (max des spots)' },
      { kw: 'BOF_MAX', desc: 'Max historique du BoF depuis t=0' },
      { kw: 'INDEX', desc: 'Numéro d\'observation (1, 2, …)' },
      { kw: 'N', desc: 'Nombre de sous-jacents' },
      { kw: 'REALVOL', desc: 'Vol réalisée annualisée du WoF depuis t=0' },
      { kw: 'S[i]', desc: 'Spot du sous-jacent i (1-indexé)' },
      { kw: 'S_MIN[i] / S_MAX[i]', desc: 'Min/max historique du sous-jacent i' },
      { kw: 'S_PREV[i]', desc: 'Spot du sous-jacent i à l\'observation précédente' },
      { kw: 'T', desc: 'Temps actuel (en années)' },
      { kw: 'WOF', desc: 'Worst-of actuel (min des spots)' },
      { kw: 'WOF_MIN', desc: 'Min historique du WoF depuis t=0' },
    ],
  },
  {
    title: 'Fonctions',
    items: [
      { kw: 'ABS(x)', desc: 'Valeur absolue' },
      { kw: 'BASKET', desc: 'Moyenne simple des spots (équipondérée)' },
      { kw: 'BASKET(w1, w2, …)', desc: 'Panier pondéré des spots' },
      { kw: 'CEIL(x) / FLOOR(x)', desc: 'Arrondi supérieur / inférieur' },
      { kw: 'EXP(x) / LOG(x) / SQRT(x)', desc: 'Exponentielle, log népérien, racine carrée' },
      { kw: 'INDIC(cond)', desc: '1 si vrai, 0 sinon' },
      { kw: 'MAX(a, b) / MIN(a, b)', desc: 'Maximum / minimum' },
      { kw: 'ROUND(x)', desc: 'Arrondi à l\'entier' },
    ],
  },
  {
    title: 'Opérateurs logiques & comparaisons',
    items: [
      { kw: '>=  <=  =  !=', desc: 'Comparateurs (= et == sont équivalents)' },
      { kw: 'AND / OR / NOT', desc: 'Et / ou / négation' },
      { kw: 'FALSE / TRUE', desc: 'Booléens' },
    ],
  },
]

store.parseScript()
</script>
