<template>
  <div class="flex flex-col gap-5">
    <div class="card">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Economics produit</h2>
          <p class="text-xs text-slate-500 mt-1">
            Définition contractuelle utilisée par le pricing et figée au booking.
          </p>
        </div>
        <div class="flex flex-wrap gap-1.5 text-[10px]">
          <span class="badge badge-muted">{{ store.underlyings.length }} sous-jacent(s)</span>
          <span class="badge badge-muted">{{ store.scriptParams.length }} paramètre(s)</span>
          <span class="badge badge-muted">{{ store.scriptConstats.length }} calendrier(s)</span>
        </div>
      </div>
    </div>

    <!-- ── Termes principaux ─────────────────────────────────── -->
    <fieldset class="card" :disabled="contractTermsLocked">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Termes principaux</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label class="label">Nominal <span class="text-red-400">*</span></label>
          <SensitiveValue mode="input">
            <input v-model="nominalRaw" @blur="formatNominal" @focus="unformatNominal"
              type="text" inputmode="numeric" class="input font-mono text-right"
              placeholder="1 000 000" />
          </SensitiveValue>
          <p v-if="!nominalValue" class="text-red-400 text-xs mt-1">Nominal requis pour le booking</p>
        </div>
        <div>
          <label class="label">Devise de règlement</label>
          <select v-model="store.globalParams.deal_ccy" class="select">
            <option>EUR</option><option>USD</option><option>GBP</option>
            <option>JPY</option><option>CHF</option><option>SGD</option>
          </select>
        </div>
      </div>
    </fieldset>

    <!-- ── Dates économiques ─────────────────────────────────── -->
    <fieldset class="card" :disabled="contractTermsLocked">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Dates économiques</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label class="label">StartDate / strike <span class="text-slate-600 font-normal">(fixing S₀)</span>
            <HelpTip text="Fixing initial du panier, distinct de la première observation de payoff, et origine de l'axe des temps du moteur. Les performances du produit sont mesurées relativement aux niveaux S₀ constatés à cette date." />
          </label>
          <input v-model="store.startDate" type="date" class="input" aria-label="StartDate / date de strike"
                 :aria-required="!!store.initialFixingName"
                 :readonly="datesLocked"
                 :class="[datesLocked ? 'bg-slate-800/40 text-slate-500 cursor-not-allowed' : '', marque.classe(cheminGlobal('strike_date'))]" />
          <p v-if="store.initialFixingName && !store.startDate" class="text-xs text-slate-500 mt-1">
            Requise pour fixer les niveaux initiaux, avant la première observation.
          </p>
          <p v-if="datesLocked" class="text-[10px] text-slate-500 mt-0.5">
            {{ contractTermsLocked ? 'Figée au booking.' : 'Figée sur un avenant — le passé a été rejoué dessus.' }}
          </p>
        </div>
        <div>
          <label class="label">Value date
            <HelpTip text="Date d'échange initial du cash et date à laquelle le prix est exprimé. Elle reste distincte de la strike date, qui ancre l'axe du moteur." />
          </label>
          <input v-model="store.globalParams.value_date" type="date" class="input"
                 :readonly="datesLocked"
                 :class="[datesLocked ? 'bg-slate-800/40 text-slate-500 cursor-not-allowed' : '', marque.classe(cheminGlobal('value_date'))]" />
          <p v-if="datesLocked" class="text-[10px] text-slate-500 mt-0.5">
            {{ contractTermsLocked ? 'Figée au booking.' : 'Figée sur un avenant — le passé a été rejoué dessus.' }}
          </p>
        </div>
        <div>
          <label class="label">Maturité
            <HelpTip width="w-72" text="Dernière date de constatation du produit, tous échéanciers confondus, après convention de jour ouvré. La modifier déplace les constatations qui tombaient à l'ancienne maturité ; un échéancier qui se termine avant ne bouge pas. AT MATURITY utilise cette date. La date est prise en compte en quittant le champ." />
          </label>
          <input :value="store.maturityDate" type="date" class="input"
            :readonly="contractTermsLocked"
            :class="contractTermsLocked ? 'bg-slate-800/40 text-slate-500 cursor-not-allowed' : ''"
            @blur="commitMaturity" @keydown.enter.prevent="commitMaturity" />
          <p v-if="contractTermsLocked" class="text-[10px] text-slate-500 mt-0.5">Figée au booking.</p>
          <p v-else-if="store.maturityError" class="text-[10px] text-red-400 mt-0.5">{{ store.maturityError }}</p>
        </div>
        <div>
          <label class="label">Payment date <span class="text-slate-600 font-normal">(règlement final)</span>
            <HelpTip text="Date d'échange du cash final. Elle porte l'actualisation du remboursement et peut donc modifier le prix. Proposée à maturité + 3 jours ouvrés, mais reste éditable selon le term sheet." />
          </label>
          <input v-model="store.globalParams.payment_date" type="date" class="input"
            @input="paymentDateDirty = true" />
        </div>
      </div>
    </fieldset>

    <!-- ── Paramètres PayScript ──────────────────────────────── -->
    <div class="card">
      <div class="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div>
          <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Paramètres du produit</h2>
          <p class="text-[10px] text-slate-500 mt-1">
            Toutes les déclarations PARAM du PayScript, dans leurs unités d'affichage.
          </p>
        </div>
        <button class="btn-ghost btn-sm" @click="store.leftTab = 'script'">Voir le script</button>
      </div>

      <div v-if="!store.scriptParams.length" class="text-xs text-slate-600 italic py-2">
        Aucun PARAM déclaré dans le script courant.
      </div>

      <fieldset v-else :disabled="contractTermsLocked"
                class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        <div v-for="p in store.scriptParams" :key="p.name"
             class="rounded-lg border border-slate-700 bg-slate-800/40 p-3 flex flex-col gap-2"
             :class="p.kind === 'array' ? 'sm:col-span-2 xl:col-span-3' : ''">
          <div class="flex items-start justify-between gap-2">
            <label class="label mb-0">
              {{ p.desc && p.desc !== p.name ? p.desc : p.name }}
              <span v-if="p.kind === 'array'" class="text-slate-600 font-normal normal-case">
                (par constatation)
              </span>
            </label>
            <span class="font-mono text-[9px] text-slate-600 shrink-0">{{ p.name }}</span>
          </div>

          <div class="text-[10px] text-slate-500 flex flex-wrap gap-x-2 gap-y-0.5">
            <span>Déclaré : {{ formatParamDefault(p) }}</span>
            <span v-if="marque.etat(cheminParam(p.name)) === 'modifie'" class="text-amber-400">
              Origine variante : {{ valeurLisible(marque.avant(cheminParam(p.name))) }}
            </span>
          </div>

          <template v-if="p.kind === 'array'">
            <div class="flex flex-col gap-1.5">
              <div v-for="(value, rowIndex) in store.paramOverrides[p.name]" :key="rowIndex"
                   class="grid grid-cols-[8.5rem_minmax(0,1fr)_1rem] items-center gap-1.5">
                <span class="text-[10px] text-slate-500 font-mono whitespace-nowrap">
                  Obs {{ rowIndex + 1 }}
                  <template v-if="observationDates[rowIndex]">· {{ formatDate(observationDates[rowIndex]) }}</template>
                </span>
                <SensitiveValue mode="input">
                  <div class="relative">
                    <input v-model.number="store.paramOverrides[p.name][rowIndex]"
                           type="number" step="any" class="input pr-7 py-1 text-xs text-right" />
                    <span v-if="p.is_pct" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-500">%</span>
                  </div>
                </SensitiveValue>
                <button v-if="store.paramOverrides[p.name].length > 1"
                        class="text-slate-600 hover:text-red-400 text-xs"
                        title="Supprimer cette ligne"
                        @click="store.paramOverrides[p.name].splice(rowIndex, 1)">✕</button>
              </div>
            </div>
            <p class="text-[10px] text-slate-600">
              La dernière valeur s'étend aux constatations suivantes ; une ligne en trop est ignorée.
            </p>
            <button class="text-xs text-blue-400 hover:underline self-start"
              @click="store.paramOverrides[p.name].push(store.paramOverrides[p.name].at(-1) ?? p.display_default)">
              + Ajouter une constatation
            </button>
          </template>

          <SensitiveValue v-else mode="input">
            <div class="relative">
              <input :id="`economic-param-${p.name}`"
                     v-model.number="store.paramOverrides[p.name]"
                     type="number" step="any" class="input pr-7 text-right"
                     :class="marque.classe(cheminParam(p.name))" />
              <span v-if="p.is_pct" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-500">%</span>
            </div>
          </SensitiveValue>
        </div>
      </fieldset>
    </div>

    <!-- ── Sous-jacents ──────────────────────────────────────── -->
    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Sous-jacents
          <HelpTip text="Composition contractuelle du panier. Les volatilités, dividendes, smiles, corrélations et paramètres quanto restent dans Marché & Paramètres." />
        </h2>
        <button class="btn-secondary text-xs"
                :disabled="contractTermsLocked || store.underlyings.length >= store.calculationLimits.maxUnderlyings"
                :title="contractTermsLocked
                  ? 'Panier figé au booking'
                  : store.underlyings.length >= store.calculationLimits.maxUnderlyings
                    ? `Maximum autorisé : ${store.calculationLimits.maxUnderlyings} sous-jacents` : ''"
                @click="onAddUnderlying">+ Ajouter</button>
      </div>

      <p v-if="store.underlyings.length > store.calculationLimits.underlyingWarningCount"
         class="text-[10px] text-amber-500 mb-3">
        Panier large : {{ store.underlyings.length }} sous-jacents. Le maximum autorisé est
        {{ store.calculationLimits.maxUnderlyings }}.
      </p>

      <div class="flex gap-1 mb-3 flex-wrap items-center">
        <button v-for="(underlying, index) in store.underlyings" :key="index"
          @click="store.activeUnderlyingIdx = index"
          :class="[
            'px-2.5 py-1 rounded-md text-xs font-medium transition-colors border',
            activeUIdx === index
              ? 'bg-blue-900/50 border-blue-600 text-blue-300'
              : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
          ]">
          <span class="font-semibold">{{ demo.underlyingLabel(underlying.name, index) }}</span>
          <span v-if="underlying.ticker" class="ml-1.5 opacity-50 font-mono text-[10px]">
            <SensitiveValue placeholder="···">{{ underlying.ticker }}</SensitiveValue>
          </span>
        </button>
      </div>

      <fieldset v-if="activeU" :disabled="contractTermsLocked"
                class="bg-slate-800/60 border border-slate-700 rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <span v-if="demo.enabled" class="text-sm font-semibold text-slate-300 border-b border-slate-600 pb-1">
            {{ demo.underlyingLabel(activeU.name, activeUIdx) }}
          </span>
          <input v-else v-model="activeU.name"
            class="input w-auto text-sm font-semibold bg-transparent border-0 border-b border-slate-600 rounded-none px-0 pb-1 focus:border-blue-500" />
          <button v-if="store.underlyings.length > 1 && !contractTermsLocked"
            class="text-slate-600 hover:text-red-400 text-xs ml-2"
            @click="onRemoveUnderlying">✕</button>
        </div>

        <div class="mb-1">
          <label class="label">Ticker Yahoo Finance</label>
          <SensitiveValue mode="input">
            <div class="flex gap-2 items-center">
              <select class="select text-xs flex-1" :value="activeU.ticker"
                      @change="onTickerSelect($event.target.value)">
                <option value="">— Choisir un sous-jacent —</option>
                <optgroup v-for="group in underlyingGroups" :key="group.group" :label="group.group">
                  <option v-for="item in group.items" :key="item.ticker" :value="item.ticker">{{ item.label }}</option>
                </optgroup>
              </select>
            </div>
            <input v-model="activeU.ticker" class="input font-mono mt-1 text-xs"
              placeholder="ou saisir manuellement ex: ^STOXX50E"
              @blur="onTickerBlur" />
          </SensitiveValue>
        </div>
        <details v-if="absoluteSpots || activeU.spot0" :open="absoluteSpots" class="mt-2 text-xs">
          <summary class="cursor-pointer text-slate-400">Cours en devise — scripts spécifiques</summary>
          <p class="text-slate-500 mt-2">
            Inutile pour un payoff en pourcentage : <code>Basket.yield</code> et
            <code>Basket.spot / Basket.spot0</code> utilisent directement les ratios.
          </p>
          <label class="label mt-2">Cours initial du sous-jacent ({{ activeU.ccy }})
            <SensitiveValue mode="input">
              <input type="number" min="0" step="any" class="input max-w-xs" v-model.number="activeU.spot0"
                     placeholder="Seulement pour les cours absolus" />
            </SensitiveValue>
          </label>
          <p class="text-slate-500 mt-1">
            Hypothèse de simulation si le script utilise des cours en devise.
            Les fixings contractuels sont gérés dans Events.
          </p>
        </details>
        <div class="w-32">
          <label class="label">Devise du sous-jacent</label>
          <select v-model="activeU.ccy" class="select">
            <option>EUR</option><option>USD</option><option>GBP</option>
            <option>JPY</option><option>CHF</option><option>SGD</option>
          </select>
        </div>
      </fieldset>
    </div>

    <fieldset class="card" :disabled="contractTermsLocked">
      <h2 class="label">Calendriers du script</h2>
      <PayScriptCalendars :declarations="calendarControls" :values="store.constatOverrides"
        :currency="store.globalParams.deal_ccy"
        :initial-date="store.startDate" :explicit-fixing="!!store.initialFixingName" />
    </fieldset>

    <!-- ── Aperçu consolidé ──────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
        Structure des constatations
        <HelpTip width="w-72" text="Aperçu consolidé de l'échéancier économique. Les niveaux S₀ officiels sont saisis dans Events après booking ; les clôtures affichées ici restent indicatives." />
      </h2>

      <div v-if="!previewEvents.length" class="text-xs text-slate-600 italic py-2">
        Définissez un calendrier ou lancez un pricing pour visualiser les constatations.
      </div>
      <div v-else>
        <div class="overflow-x-auto table-shell" tabindex="0" role="region" aria-label="Structure des constatations">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium pb-2 pr-3">#</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Événement</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Date</th>
                <th class="text-right text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">T (Y)</th>
                <th v-for="underlying in store.underlyings" :key="underlying.name"
                    class="text-right text-slate-500 font-medium pb-2 pr-2 whitespace-nowrap">
                  {{ underlying.ticker || underlying.name }} <span class="text-slate-600 font-normal">indicatif</span>
                </th>
                <th class="text-left text-slate-500 font-medium pb-2">Statut</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(event, index) in previewEvents" :key="`${event.date}-${index}`"
                  :class="['border-b border-slate-800/50', event.t === 0 ? 'bg-amber-950/20' : '', event.isFuture && event.t !== 0 ? 'opacity-60' : '']">
                <td class="py-1.5 pr-3 text-slate-500">{{ index + 1 }}</td>
                <td class="py-1.5 pr-3 whitespace-nowrap"
                    :class="event.t === 0 ? 'text-amber-400 font-semibold' : 'text-slate-300'">{{ event.label }}</td>
                <td class="py-1.5 pr-3 font-mono text-slate-300 whitespace-nowrap">{{ formatDate(event.date) }}</td>
                <td class="py-1.5 pr-3 font-mono text-right text-slate-400">{{ formatNumber(event.t, 4) }}</td>
                <td v-for="underlying in store.underlyings" :key="underlying.name" class="py-1.5 pr-2 text-right">
                  <span v-if="pastCloses[event.date]?.[underlying.ticker]" class="text-slate-300 font-mono text-[10px]">
                    <SensitiveValue>{{ formatNumber(pastCloses[event.date][underlying.ticker], 2) }}</SensitiveValue>
                  </span>
                  <span v-else class="text-slate-600 font-mono text-[10px]">–</span>
                </td>
                <td class="py-1.5">
                  <span class="text-[10px]" :class="event.isFuture ? 'text-slate-600' : 'text-emerald-400'">
                    {{ event.isFuture ? 'à observer' : 'constaté' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="text-[10px] text-slate-600 mt-2">
          {{ previewEvents.length }} ligne(s) · {{ store.underlyings.length }} sous-jacent(s).
          Le calendrier CONSTAT contractuel prévaut sur la grille du Monte Carlo.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { apiFetch } from '../utils/api.js'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { useVariantMark, cheminConstat, cheminGlobal, cheminParam, valeurLisible } from '../composables/useVariantMark.js'
import { underlyingGroups, ensureUnderlyings } from '../data/commonUnderlyings.js'
import { formatDate, formatInt, formatNumber } from '../utils/format.js'
import PayScriptCalendars from './PayScriptCalendars.vue'
import { usesAbsoluteSpots } from '../utils/payscriptEconomics.js'
import HelpTip from './HelpTip.vue'
import { useObservationPreview } from '../composables/useObservationPreview.js'
import SensitiveValue from './SensitiveValue.vue'

const store = usePricingStore()
const absoluteSpots = computed(() => usesAbsoluteSpots(store.script))
const demo = useDemoModeStore()
const marque = useVariantMark(store)

onMounted(ensureUnderlyings)

const contractTermsLocked = computed(() => store.contractTermsLocked)
const datesFigees = computed(() =>
  store.variantInfo && (store.variantInfo.mode || 'avenant') === 'avenant')
const datesLocked = computed(() => contractTermsLocked.value || datesFigees.value)

function parseNominal(value) {
  return parseFloat(String(value ?? '').replace(/\s/g, '').replace(',', '.')) || 0
}

const nominalRaw = ref(formatInt(store.globalParams.nominal || 1_000_000))
const nominalValue = computed(() => parseNominal(nominalRaw.value))

watch(nominalRaw, (value) => {
  store.globalParams.nominal = parseNominal(value)
})
watch(() => store.globalParams.nominal, (value) => {
  if (Number(value || 0) !== nominalValue.value) nominalRaw.value = formatInt(value || 0)
})

function formatNominal() {
  if (nominalValue.value) nominalRaw.value = formatInt(nominalValue.value)
}
function unformatNominal(event) {
  nominalRaw.value = String(nominalValue.value || '')
  if (event?.target) nextTick(() => event.target.select())
}

function addBizDays(isoDate, days) {
  const date = new Date(isoDate)
  let added = 0
  while (added < days) {
    date.setDate(date.getDate() + 1)
    if (date.getDay() !== 0 && date.getDay() !== 6) added += 1
  }
  return date.toISOString().split('T')[0]
}

function usableDate(iso) {
  if (!iso) return false
  const year = Number(String(iso).slice(0, 4))
  return Number.isFinite(year) && year >= 1990 && year <= 2200
}

const paymentDateDirty = ref(!!store.globalParams.payment_date)
let proposingPaymentDate = false

watch(() => store.globalParams.payment_date, (value) => {
  if (!proposingPaymentDate) paymentDateDirty.value = !!value
}, { immediate: true })

// Only the proposal for the latest maturity may land: opening a product moves
// the maturity several times in a row, and an older answer arriving last
// would propose a payment date for a maturity that no longer exists.
let proposalRevision = 0

async function proposePaymentDate(maturity) {
  const revision = ++proposalRevision
  if (contractTermsLocked.value || !usableDate(maturity) || paymentDateDirty.value) return
  try {
    const response = await apiFetch('/api/calendar/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: maturity, currency: store.globalParams.deal_ccy || 'EUR', business_days: 3 }),
    })
    if (response.ok) {
      const proposed = (await response.json()).date
      if (revision === proposalRevision && !paymentDateDirty.value) setProposedPaymentDate(proposed)
      return
    }
  } catch { /* repli week-end uniquement ci-dessous */ }
  if (revision === proposalRevision && !paymentDateDirty.value) {
    setProposedPaymentDate(addBizDays(maturity, 3))
  }
}

function setProposedPaymentDate(date) {
  proposingPaymentDate = true
  store.globalParams.payment_date = date
  nextTick(() => { proposingPaymentDate = false })
}

watch(() => store.maturityDate, proposePaymentDate, { immediate: true })
watch(() => [store.maturityDate, store.globalParams.strike_date],
  () => store.syncTenorFromMaturity(), { immediate: true })

// The maturity is committed on leaving the field (or on Enter), never on each
// keystroke: a date input emits a complete date for every segment typed, and
// an intermediate year would move the terminal constatations onto a date
// that was only passing through.
function commitMaturity(event) {
  if (contractTermsLocked.value) return
  const value = event.target.value
  if (value === store.maturityDate) return
  if (!store.setMaturityDate(value)) event.target.value = store.maturityDate
}

function formatParamDefault(param) {
  const value = param.display_default
  if (Array.isArray(value)) return value.map(item => `${item}${param.is_pct ? '%' : ''}`).join(' · ')
  return `${value ?? '—'}${param.is_pct && value != null ? '%' : ''}`
}

const activeUIdx = computed(() => store.activeUnderlyingIdx)
const activeU = computed(() => store.underlyings[activeUIdx.value] ?? store.underlyings[0])
// Every CONSTAT keeps its card, `MATURITE` included: its window and convention
// are typed there. The Maturity field moves the terminal constatations,
// whatever their name.
const calendarControls = computed(() => store.scriptConstats.filter(c => c.role !== 'initial_fixing' || c.reduction))

function onAddUnderlying() {
  if (!contractTermsLocked.value) store.addUnderlying()
}
function onRemoveUnderlying() {
  if (!contractTermsLocked.value) store.removeUnderlying(activeUIdx.value)
}
function onTickerSelect(ticker) {
  if (contractTermsLocked.value) return
  activeU.value.ticker = ticker
}

function onTickerBlur() {
  if (contractTermsLocked.value) return
  activeU.value.ticker = activeU.value.ticker.trim().toUpperCase()
}

const { previewEvents, datesObservations: observationDates, closesPassees: pastCloses } = useObservationPreview(
  store, () => store.startDate, () => store.globalParams.deal_ccy)
</script>
