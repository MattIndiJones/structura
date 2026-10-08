<template>
  <div class="flex flex-col gap-4">

    <!-- Toolbar -->
    <div class="flex items-center gap-2 flex-wrap">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mr-auto">PayScript</h2>

      <select class="select text-xs w-auto" :disabled="store.contractTermsLocked"
              @change="loadExample($event.target.value); $event.target.value=''">
        <option value="">Modèles génériques…</option>
        <option value="__blank__">— Script libre (vide) —</option>
        <optgroup v-for="(items, group) in groupedTemplates" :key="group" :label="group">
          <option v-for="t in items" :key="t.key" :value="t.key">{{ t.label }}</option>
        </optgroup>
      </select>

      <PayScriptPresetPicker :disabled="store.contractTermsLocked" :currency="store.globalParams.deal_ccy"
                            :start-date="store.startDate" :underlying-count="store.underlyings.length"
                            :on-apply="store.loadFromPreset" />

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

    <PayScriptConfigurations v-if="!store.contractTermsLocked" />

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
import PayScriptConfigurations from './PayScriptConfigurations.vue'
import PayScriptPresetPicker from './PayScriptPresetPicker.vue'
import { templateMeta, examples } from '../data/payscriptTemplates.js'

const store = usePricingStore()
const notice = ref('')

const groupedTemplates = computed(() => {
  const groups = {}
  for (const t of templateMeta) {
    ;(groups[t.group] ||= []).push(t)
  }
  return groups
})


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

// Loading a model starts a blank contract; values live in optional configurations.
async function loadExample(key) {
  if (!key || store.contractTermsLocked) return
  const text = key === '__blank__' ? examples.call : examples[key]
  if (!text) return
  await store.loadFromProductModel({ script: text, underlyings: { min: 1, max: 12 } })
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
  { title: 'Panier et fixing initial', items: [
    { kw: 'UNDERLYING Basket', desc: 'Panier lié aux sous-jacents Economics, dans le même ordre' },
    { kw: 'CONSTAT StartDate', desc: 'Date du fixing initial ; distincte des observations du payoff' },
    { kw: 'Basket.spot0 = Basket.spot@StartDate', desc: 'Dans AT StartDate : fixe les références individuelles une seule fois' },
    { kw: 'Basket.yield', desc: 'Ratios spot courant / spot initial : 1,10 = 110 %' },
    { kw: 'WORSTOF / BESTOF / AVG(Basket.yield)', desc: 'Minimum / maximum / moyenne équipondérée des ratios' },
  ] },
  { title: 'Termes et calendrier', items: [
    { kw: 'PARAM COUPON', desc: 'Pourcentage obligatoire dans Economics, sans valeur par défaut' },
    { kw: 'PARAM() M_AC_BAR', desc: 'Tableau par observation ; dernière valeur prolongée' },
    { kw: 'PARAM X = 1.5', desc: 'Valeur brute avec défaut explicite ; = 8% déclare un défaut en pourcentage' },
    { kw: 'CONSTAT() ObservationDates', desc: 'Première observation incluse ; dates saisies dans Economics' },
    { kw: 'AT Date FROM ObservationDates:', desc: 'Exécute le bloc à chaque observation ; INDEX commence à 1' },
    { kw: 'AT ObservationDates.last:', desc: 'Dernière observation ; remboursement final si le produit est vivant' },
    { kw: 'MIN / MAX / AVG après CONSTAT', desc: 'Fenêtre de fixing par sous-jacent, avant agrégation du panier' },
    { kw: 'PERIOD', desc: 'Fenêtre depuis la constatation précédente ; StartDate ouvre la première période' },
  ] },
  { title: 'Flux et état', items: [
    { kw: 'PAY expression "Libellé"', desc: 'Une ligne par coupon, capital ou put ; montants en fraction du nominal' },
    { kw: 'PAY 1 / PAY -KI * MAX(1 - PERF, 0)', desc: 'Deux lignes distinctes : remboursement nominal et perte sur put vendu' },
    { kw: 'STOP', desc: 'Arrête le produit et empêche tout second remboursement' },
    { kw: 'SET / IF / ELSE / ACCRUE', desc: 'Variables, conditions et accumulation' },
    { kw: 'COUPON * INDEX', desc: 'Cumul d’un coupon par période, sans annualisation implicite' },
    { kw: 'INDIC(condition)', desc: '1 si la condition est vraie, 0 sinon' },
    { kw: 'M_', desc: 'Barrière surveillée par Booking ; observable et direction déduits de son usage' },
    { kw: 'WOF_MIN / BOF_MAX / S_MIN[i]', desc: 'Extrema historiques depuis le fixing initial (barrières américaines)' },
  ] },
]

store.parseScript()
</script>
