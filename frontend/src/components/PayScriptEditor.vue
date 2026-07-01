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

      <select class="select text-xs w-auto" @change="loadExample($event.target.value); $event.target.value=''">
        <option value="">{{ expertMode ? 'Exemples (expert)…' : 'Exemples…' }}</option>
        <optgroup label="Autocall">
          <option value="autocall_athena">Autocall Athena 3Y</option>
          <option value="autocall_phoenix">Phoenix 3Y (coupon conditionnel)</option>
          <option value="autocall_worst_of">Worst-of Athena 2 actifs</option>
        </optgroup>
        <optgroup label="Options">
          <option value="call_vanilla">Call Vanille</option>
          <option value="put_vanilla">Put Vanille</option>
          <option value="call_spread">Call Spread</option>
          <option value="digital">Digital (binaire)</option>
        </optgroup>
        <optgroup label="Produits à capital">
          <option value="capital_garanti">Capital Garanti 5Y</option>
          <option value="reverse_convertible">Reverse Convertible</option>
          <option value="twin_win">Twin Win</option>
          <option value="booster">Booster 3Y</option>
        </optgroup>
        <optgroup label="Validation">
          <option value="zcb">ZCB (test actualisation)</option>
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
    <Teleport to="body">
      <div v-if="saveModal.open"
           class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 px-4"
           @click.self="saveModal.open = false">
        <div class="card w-full max-w-sm flex flex-col gap-4">
          <div class="text-sm font-bold text-slate-200">Sauvegarder le script</div>

          <div v-if="saveModal.error"
               class="bg-red-950/60 border border-red-800 rounded px-3 py-2 text-xs text-red-300">
            {{ saveModal.error }}
          </div>

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

          <div class="flex gap-2">
            <button class="btn-primary text-xs flex-1" :disabled="saving" @click="doSave">
              <span v-if="saving" class="w-3 h-3 border border-white/60 border-t-transparent rounded-full animate-spin inline-block mr-1.5"></span>
              Sauvegarder
            </button>
            <button class="btn-secondary text-xs flex-1" @click="saveModal.open = false">Annuler</button>
          </div>
        </div>
      </div>
    </Teleport>

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
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Paramètres du script</div>
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div v-for="p in store.scriptParams" :key="p.name" class="flex flex-col gap-1">
          <label class="label">{{ p.name }}</label>
          <SensitiveValue mode="input">
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

    <!-- Dynamic CONSTAT inputs (mode expert — calendrier) -->
    <div v-if="store.scriptConstats.length > 0" class="card">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Calendrier du script (CONSTAT)</div>
      <div class="flex flex-col gap-3">
        <div v-for="c in store.scriptConstats" :key="c.name"
             class="bg-slate-800/60 border border-slate-700 rounded-lg p-3">
          <div class="text-xs font-semibold text-slate-300 mb-2">{{ c.name }}</div>

          <!-- CONSTAT : une date unique -->
          <div v-if="c.kind === 'single'" class="text-xs max-w-xs">
            <label class="label">Date</label>
            <SensitiveValue mode="input">
              <input type="date" v-model="store.constatOverrides[c.name]" class="input" />
            </SensitiveValue>
          </div>

          <!-- CONSTAT() / CONSTAT()() -->
          <div v-else class="flex flex-wrap gap-4 text-xs items-start">
            <div class="flex flex-col gap-2 min-w-[160px]">
              <div>
                <label class="label">Date de début</label>
                <SensitiveValue mode="input">
                  <input type="date" v-model="store.constatOverrides[c.name].start_date" class="input" />
                </SensitiveValue>
              </div>
              <div>
                <label class="label">Date de fin</label>
                <SensitiveValue mode="input">
                  <input type="date" v-model="store.constatOverrides[c.name].end_date" class="input" />
                </SensitiveValue>
              </div>
              <div>
                <label class="label">Date de roll</label>
                <SensitiveValue mode="input">
                  <input type="date" v-model="store.constatOverrides[c.name].roll_date" class="input" />
                </SensitiveValue>
              </div>
            </div>
            <div class="flex flex-col gap-2 w-36 shrink-0">
              <div>
                <label class="label">Fréquence</label>
                <div class="flex gap-1">
                  <input type="number" min="1" v-model.number="store.constatOverrides[c.name].frequency.value"
                         class="input w-14" />
                  <select v-model="store.constatOverrides[c.name].frequency.unit" class="select">
                    <option value="D">D</option>
                    <option value="M">M</option>
                    <option value="Y">Y</option>
                  </select>
                </div>
              </div>
              <div>
                <label class="label">Stub</label>
                <select v-model="store.constatOverrides[c.name].stub" class="select">
                  <option value="short_last">Short Last</option>
                  <option value="long_last">Long Last</option>
                  <option value="short_first">Short First</option>
                  <option value="long_first">Long First</option>
                </select>
              </div>
              <div v-if="c.kind === 'nested_schedule'">
                <label class="label">Sous-fréq.</label>
                <div class="flex gap-1">
                  <input type="number" min="1" v-model.number="store.constatOverrides[c.name].sub_frequency.value"
                         class="input w-14" />
                  <select v-model="store.constatOverrides[c.name].sub_frequency.unit" class="select">
                    <option value="D">D</option>
                    <option value="M">M</option>
                    <option value="Y">Y</option>
                  </select>
                </div>
              </div>
            </div>
          </div>

          <!-- Aperçu calendrier -->
          <div v-if="c.kind !== 'single'" class="mt-2 text-xs">
            <button class="text-blue-400 hover:underline" @click="previewConstat(c.name)">
              Aperçu du calendrier
            </button>
            <span v-if="previewErrors[c.name]" class="text-red-400 ml-2">⚠ {{ previewErrors[c.name] }}</span>
            <span v-else-if="previews[c.name]" class="text-slate-500 ml-2">
              <SensitiveValue>
                — {{ previews[c.name].dates.length }} dates générées
                ({{ previews[c.name].dates[0] }} → {{ previews[c.name].dates[previews[c.name].dates.length - 1] }})
              </SensitiveValue>
            </span>
          </div>
        </div>
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
  </div>
</template>

<script setup>
import { ref, reactive, nextTick } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import SensitiveValue from './SensitiveValue.vue'

const store = usePricingStore()
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
  } catch (e) {
    saveModal.error = e.message
  } finally {
    saving.value = false
  }
}

const previews = reactive({})
const previewErrors = reactive({})

// ── Date helpers ───────────────────────────────────────────────────
function isoToday() {
  return new Date().toISOString().slice(0, 10)
}

function addYears(n) {
  const d = new Date()
  d.setFullYear(d.getFullYear() + n)
  return d.toISOString().slice(0, 10)
}

// ── Normal examples ────────────────────────────────────────────────
const examples = {
  autocall_athena: `# Autocall Athena 3 ans
PARAM COUPON = 8%
PARAM AC_BAR = 100%
PARAM KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_phoenix: `# Phoenix 3 ans — coupon conditionnel
PARAM COUPON = 10%
PARAM AC_BAR = 100%
PARAM CPN_BAR = 80%
PARAM KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= AC_BAR)
  SET CPN  = INDIC(WOF >= CPN_BAR)
  PAY CPN * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_worst_of: `# Worst-of Athena 2 sous-jacents
PARAM COUPON = 12%
PARAM AC_BAR = 100%
PARAM KI_BAR = 55%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF_MIN < KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  call_vanilla: `# Call Vanille
PARAM STRIKE = 100%

AT MATURITY:
  PAY MAX(0, WOF - STRIKE)`,

  put_vanilla: `# Put Vanille
PARAM STRIKE = 100%

AT MATURITY:
  PAY MAX(0, STRIKE - WOF)`,

  call_spread: `# Call Spread 100%-120%
PARAM K1 = 100%
PARAM K2 = 120%

AT MATURITY:
  PAY MAX(0, MIN(WOF - K1, K2 - K1))`,

  digital: `# Digital (option binaire)
PARAM STRIKE = 100%
PARAM REBATE = 10%

AT MATURITY:
  SET ITM = INDIC(WOF >= STRIKE)
  PAY ITM * REBATE`,

  capital_garanti: `# Capital Garanti 5 ans
PARAM PART = 80%
PARAM STRIKE = 100%

AT MATURITY:
  PAY 1
  PAY MAX(0, WOF - STRIKE) * PART`,

  reverse_convertible: `# Reverse Convertible 1 an
PARAM COUPON = 10%
PARAM BAR = 80%

AT MATURITY:
  PAY COUPON
  SET KI = INDIC(WOF < BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  twin_win: `# Twin Win 3 ans
PARAM CAP = 150%
PARAM BAR = 70%

AT MATURITY:
  SET BREACHED = INDIC(WOF_MIN < BAR)
  SET UPS = MIN(CAP, MAX(1, WOF))
  SET DNS = MIN(CAP, MAX(1, 2 - WOF))
  PAY (1 - BREACHED) * MAX(UPS, DNS)
  PAY BREACHED * WOF`,

  booster: `# Booster 3 ans (levier haussier)
PARAM PART = 200%
PARAM CAP = 140%
PARAM FLOOR = 100%

AT MATURITY:
  SET PERF = WOF
  SET BOOSTED = MIN(CAP, FLOOR + (PERF - 1) * PART)
  SET DOWN = MIN(1, PERF)
  SET IS_UP = INDIC(PERF >= 1)
  PAY IS_UP * BOOSTED
  PAY (1 - IS_UP) * DOWN`,

  zcb: `# ZCB — validation actualisation
# Prix théorique = exp(-r * T)
AT MATURITY:
  PAY 1`,
}

// ── Expert examples (CONSTAT) ──────────────────────────────────────
const expertExamples = {
  autocall_athena: `# Autocall Athena 3 ans — mode expert
PARAM COUPON = 8%
PARAM AC_BAR = 100%
PARAM KI_BAR = 60%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF < KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_phoenix: `# Phoenix 3 ans — mode expert
PARAM COUPON = 10%
PARAM AC_BAR = 100%
PARAM CPN_BAR = 80%
PARAM KI_BAR = 60%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= AC_BAR)
  SET CPN  = INDIC(WOF >= CPN_BAR)
  PAY CPN * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF < KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_worst_of: `# Worst-of Athena 2 sous-jacents — mode expert
PARAM COUPON = 12%
PARAM AC_BAR = 100%
PARAM KI_BAR = 55%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF_MIN < KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  call_vanilla: `# Call Vanille — mode expert
PARAM STRIKE = 100%

CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, WOF - STRIKE)`,

  put_vanilla: `# Put Vanille — mode expert
PARAM STRIKE = 100%

CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, STRIKE - WOF)`,

  call_spread: `# Call Spread 100%-120% — mode expert
PARAM K1 = 100%
PARAM K2 = 120%

CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, MIN(WOF - K1, K2 - K1))`,

  digital: `# Digital (option binaire) — mode expert
PARAM STRIKE = 100%
PARAM REBATE = 10%

CONSTAT MATURITE

AT MATURITE:
  SET ITM = INDIC(WOF >= STRIKE)
  PAY ITM * REBATE`,

  capital_garanti: `# Capital Garanti 5 ans — mode expert
PARAM PART = 80%
PARAM STRIKE = 100%

CONSTAT MATURITE

AT MATURITE:
  PAY 1
  PAY MAX(0, WOF - STRIKE) * PART`,

  reverse_convertible: `# Reverse Convertible 1 an — mode expert
PARAM COUPON = 10%
PARAM BAR = 80%

CONSTAT MATURITE

AT MATURITE:
  PAY COUPON
  SET KI = INDIC(WOF < BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  twin_win: `# Twin Win 3 ans — mode expert
PARAM CAP = 150%
PARAM BAR = 70%

CONSTAT MATURITE

AT MATURITE:
  SET BREACHED = INDIC(WOF_MIN < BAR)
  SET UPS = MIN(CAP, MAX(1, WOF))
  SET DNS = MIN(CAP, MAX(1, 2 - WOF))
  PAY (1 - BREACHED) * MAX(UPS, DNS)
  PAY BREACHED * WOF`,

  booster: `# Booster 3 ans — mode expert
PARAM PART = 200%
PARAM CAP = 140%
PARAM FLOOR = 100%

CONSTAT MATURITE

AT MATURITE:
  SET PERF = WOF
  SET BOOSTED = MIN(CAP, FLOOR + (PERF - 1) * PART)
  SET DOWN = MIN(1, PERF)
  SET IS_UP = INDIC(PERF >= 1)
  PAY IS_UP * BOOSTED
  PAY (1 - IS_UP) * DOWN`,

  zcb: `# ZCB — validation actualisation — mode expert
CONSTAT MATURITE

AT MATURITE:
  PAY 1`,
}

// ── Expert CONSTAT pre-fill (dates computed from today) ────────────
function getExpertConstatDefaults(key) {
  const t0 = isoToday()

  // Products with CONSTAT() OBSERVATIONS (annual schedule)
  const scheduleMap = {
    autocall_athena:   3,
    autocall_phoenix:  3,
    autocall_worst_of: 3,
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
  }

  if (key in scheduleMap) {
    const endDate = addYears(scheduleMap[key])
    return { name: 'OBSERVATIONS', kind: 'schedule', values: {
      start_date: t0, end_date: endDate, roll_date: endDate,
      frequency: { value: 1, unit: 'Y' }, stub: 'short_last',
    }}
  }

  if (key in singleMap) {
    return { name: 'MATURITE', kind: 'single', values: addYears(singleMap[key]) }
  }

  return null
}

// ── Load example ───────────────────────────────────────────────────
async function loadExample(key) {
  if (!key) return
  Object.keys(store.paramOverrides).forEach(k => delete store.paramOverrides[k])

  if (expertMode.value) {
    store.script = expertExamples[key] || examples[key] || ''
    await store.parseScript()

    const def = getExpertConstatDefaults(key)
    if (def && def.name in store.constatOverrides) {
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
const tenorStr = t => (t && t.value) ? `${t.value}${t.unit}` : null

async function previewConstat(name) {
  delete previewErrors[name]
  try {
    const v = store.constatOverrides[name]
    previews[name] = await store.fetchSchedulePreview({
      start_date: v.start_date, end_date: v.end_date, roll_date: v.roll_date,
      frequency: tenorStr(v.frequency), stub: v.stub,
      sub_frequency: tenorStr(v.sub_frequency),
    })
  } catch (e) {
    previewErrors[name] = e.message
  }
}

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
