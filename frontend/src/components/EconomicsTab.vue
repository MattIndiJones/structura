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
    <div class="card">
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
    </div>

    <!-- ── Dates économiques ─────────────────────────────────── -->
    <div class="card">
      <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">Dates économiques</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label class="label">Strike date <span class="text-slate-600 font-normal">(fixing S₀)</span>
            <HelpTip text="Première constatation et origine de l'axe des temps du moteur. Les performances du produit sont mesurées relativement aux niveaux S₀ constatés à cette date." />
          </label>
          <input v-model="store.globalParams.strike_date" type="date" class="input"
                 :readonly="datesFigees"
                 :class="[datesFigees ? 'bg-slate-800/40 text-slate-500 cursor-not-allowed' : '', marque.classe(cheminGlobal('strike_date'))]" />
          <p v-if="datesFigees" class="text-[10px] text-slate-500 mt-0.5">
            Figée sur un avenant — le passé a été rejoué dessus.
          </p>
        </div>
        <div>
          <label class="label">Value date
            <HelpTip text="Date d'échange initial du cash et date à laquelle le prix est exprimé. Elle reste distincte de la strike date, qui ancre l'axe du moteur." />
          </label>
          <input v-model="store.globalParams.value_date" type="date" class="input"
                 :readonly="datesFigees"
                 :class="[datesFigees ? 'bg-slate-800/40 text-slate-500 cursor-not-allowed' : '', marque.classe(cheminGlobal('value_date'))]" />
          <p v-if="datesFigees" class="text-[10px] text-slate-500 mt-0.5">
            Figée sur un avenant — le passé a été rejoué dessus.
          </p>
        </div>
        <div>
          <label class="label">Maturité
            <HelpTip text="Dernière constatation contractuelle. Elle est dérivée du calendrier CONSTAT lorsqu'il existe, sinon de la maturité T ancrée sur la strike date." />
          </label>
          <input :value="store.maturityDate" type="date"
            class="input bg-slate-800/40 text-slate-500 cursor-not-allowed" readonly />
        </div>
        <div>
          <label class="label">Payment date <span class="text-slate-600 font-normal">(règlement final)</span>
            <HelpTip text="Date d'échange du cash final. Elle porte l'actualisation du remboursement et peut donc modifier le prix. Proposée à maturité + 3 jours ouvrés, mais reste éditable selon le term sheet." />
          </label>
          <input v-model="store.globalParams.payment_date" type="date" class="input"
            @input="paymentDateDirty = true" />
        </div>
      </div>
    </div>

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

      <div v-else class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
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
      </div>
    </div>

    <!-- ── Sous-jacents ──────────────────────────────────────── -->
    <div class="card">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Sous-jacents
          <HelpTip text="Composition contractuelle du panier. Les volatilités, dividendes, smiles, corrélations et paramètres quanto restent dans Marché & Paramètres." />
        </h2>
        <button class="btn-secondary text-xs" @click="onAddUnderlying">+ Ajouter</button>
      </div>

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

      <div v-if="activeU" class="bg-slate-800/60 border border-slate-700 rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <span v-if="demo.enabled" class="text-sm font-semibold text-slate-300 border-b border-slate-600 pb-1">
            {{ demo.underlyingLabel(activeU.name, activeUIdx) }}
          </span>
          <input v-else v-model="activeU.name"
            class="input w-auto text-sm font-semibold bg-transparent border-0 border-b border-slate-600 rounded-none px-0 pb-1 focus:border-blue-500" />
          <button v-if="store.underlyings.length > 1"
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
              <button class="btn-secondary text-lg px-3 flex-shrink-0" title="Charger σ, q depuis Yahoo Finance"
                :disabled="store.loading || !activeU.ticker" @click="store.loadYfOne(activeUIdx)">📡</button>
            </div>
            <input v-model="activeU.ticker" class="input font-mono mt-1 text-xs"
              placeholder="ou saisir manuellement ex: ^STOXX50E"
              @focus="onTickerFocus" @blur="onTickerBlur" />
          </SensitiveValue>
        </div>
        <div v-if="store.yfStatus" class="text-xs mb-2 leading-relaxed"
             :class="store.yfStatus.startsWith('⚠') ? 'text-amber-400' : 'text-green-400'">
          <SensitiveValue placeholder="Données chargées">{{ store.yfStatus }}</SensitiveValue>
        </div>

        <div class="w-32">
          <label class="label">Devise du sous-jacent</label>
          <select v-model="activeU.ccy" class="select">
            <option>EUR</option><option>USD</option><option>GBP</option>
            <option>JPY</option><option>CHF</option><option>SGD</option>
          </select>
        </div>
      </div>
    </div>

    <!-- ── Calendriers du script ─────────────────────────────── -->
    <div v-if="store.scriptConstats.length" class="card">
      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Échéanciers du script (CONSTAT)
        <HelpTip width="w-72" text="Chaque CONSTAT déclaré dans le script reçoit ici ses dates, fréquences, conventions de jour ouvré et délais de règlement. Ces valeurs sont utilisées par le moteur puis figées au booking." />
      </div>
      <div class="flex flex-col gap-3">
        <div v-for="calendar in store.scriptConstats" :key="calendar.name"
             class="bg-slate-800/60 border border-slate-700 rounded-lg p-3">
          <div class="text-xs font-semibold text-slate-300 mb-2 flex items-center gap-2">
            {{ calendar.name }}
            <span v-if="calendar.reduction"
                  class="px-1.5 py-0.5 rounded bg-blue-900/60 text-blue-300 text-[10px] font-bold">
              {{ calendar.reduction }} sur période
            </span>
            <HelpTip v-if="calendar.reduction" width="w-80"
                     :text="`Chaque date de ce CONSTAT applique ${calendar.reduction} aux cours de chaque sous-jacent sur la fenêtre définie ci-dessous, avant l'agrégation worst-of, best-of ou panier.`" />
          </div>

          <template v-if="calendar.kind === 'single'">
            <div class="text-xs max-w-xs">
              <label class="label">Date</label>
              <SensitiveValue mode="input">
                <input v-if="calendar.reduction" type="date" v-model="store.constatOverrides[calendar.name].date" class="input" />
                <input v-else type="date" v-model="store.constatOverrides[calendar.name]" class="input" />
              </SensitiveValue>
            </div>
            <div v-if="calendar.reduction" class="flex flex-wrap gap-3 items-end text-xs mt-2">
              <ConstatWindowFields :scope="calendar.window_scope"
                                   :valeurs="store.constatOverrides[calendar.name]"
                                   :apercu="windowPreviews[calendar.name]" />
            </div>
          </template>

          <div v-else class="flex flex-col gap-2 text-xs">
            <div class="flex flex-wrap gap-3 items-end">
              <div>
                <label class="label">Date de début
                  <HelpTip text="Début de la première période. Ce point initialise la grille mais n'est pas lui-même une observation : les constatations commencent à la date suivante générée." />
                </label>
                <SensitiveValue mode="input">
                  <input type="date" v-model="store.constatOverrides[calendar.name].start_date" class="input"
                         :class="marque.classe(cheminConstat(calendar.name, 'start_date'))" />
                </SensitiveValue>
              </div>
              <div>
                <label class="label">Date de fin</label>
                <SensitiveValue mode="input">
                  <input type="date" v-model="store.constatOverrides[calendar.name].end_date" class="input"
                         :class="marque.classe(cheminConstat(calendar.name, 'end_date'))" />
                </SensitiveValue>
              </div>
              <div>
                <label class="label">Date de roll</label>
                <SensitiveValue mode="input">
                  <input type="date" v-model="store.constatOverrides[calendar.name].roll_date" class="input"
                         :class="marque.classe(cheminConstat(calendar.name, 'roll_date'))" />
                </SensitiveValue>
              </div>
              <div>
                <label class="label">Fréquence</label>
                <div class="flex gap-1">
                  <input type="number" min="1" v-model.number="store.constatOverrides[calendar.name].frequency.value" class="input w-14" />
                  <select v-model="store.constatOverrides[calendar.name].frequency.unit" class="select">
                    <option value="D">D</option><option value="M">M</option><option value="Y">Y</option>
                  </select>
                </div>
              </div>
              <ConstatWindowFields v-if="calendar.reduction"
                                   :scope="calendar.window_scope"
                                   :valeurs="store.constatOverrides[calendar.name]"
                                   :apercu="windowPreviews[calendar.name]" />
              <div>
                <label class="label">Convention
                  <HelpTip text="Ajustement appliqué lorsqu'une constatation tombe un jour fermé sur le calendrier de la devise de règlement." />
                </label>
                <select v-model="store.constatOverrides[calendar.name].convention" class="select">
                  <option value="none">Aucun ajustement</option>
                  <option value="following">Jour ouvré suivant</option>
                  <option value="modified_following">Suivant, sauf changement de mois</option>
                  <option value="preceding">Jour ouvré précédent</option>
                  <option value="modified_preceding">Précédent, sauf changement de mois</option>
                </select>
              </div>
              <div>
                <label class="label">Règlement
                  <HelpTip text="Nombre de jours ouvrés entre la constatation et l'échange du cash correspondant. C'est la date de paiement qui porte l'actualisation." />
                </label>
                <div class="flex items-center gap-1">
                  <input type="number" min="0" max="15" class="input w-16"
                         v-model.number="store.constatOverrides[calendar.name].settlement_lag" />
                  <span class="text-[10px] text-slate-500 whitespace-nowrap">j. ouvrés</span>
                </div>
              </div>
              <div>
                <label class="label">Stub</label>
                <select v-model="store.constatOverrides[calendar.name].stub" class="select">
                  <option value="short_last">Short Last</option><option value="long_last">Long Last</option>
                  <option value="short_first">Short First</option><option value="long_first">Long First</option>
                </select>
              </div>
              <div v-if="calendar.kind === 'nested_schedule'">
                <label class="label">Sous-fréquence</label>
                <div class="flex gap-1">
                  <input type="number" min="1" v-model.number="store.constatOverrides[calendar.name].sub_frequency.value" class="input w-14" />
                  <select v-model="store.constatOverrides[calendar.name].sub_frequency.unit" class="select">
                    <option value="D">D</option><option value="M">M</option><option value="Y">Y</option>
                  </select>
                </div>
              </div>
            </div>
            <ObservationSchedule class="mt-1" :request="scheduleRequest(calendar)"
                                 :window-frequency="samplingFrequency(calendar)" />
          </div>
        </div>
      </div>
    </div>

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
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { useVariantMark, cheminConstat, cheminGlobal, cheminParam, valeurLisible } from '../composables/useVariantMark.js'
import { underlyingGroups, ensureUnderlyings } from '../data/commonUnderlyings.js'
import { formatDate, formatInt, formatNumber } from '../utils/format.js'
import ConstatWindowFields from './ConstatWindowFields.vue'
import HelpTip from './HelpTip.vue'
import ObservationSchedule from './ObservationSchedule.vue'
import SensitiveValue from './SensitiveValue.vue'

const store = usePricingStore()
const demo = useDemoModeStore()
const marque = useVariantMark(store)

onMounted(ensureUnderlyings)

const datesFigees = computed(() =>
  store.variantInfo && (store.variantInfo.mode || 'avenant') === 'avenant')

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

async function proposePaymentDate(maturity) {
  if (!usableDate(maturity) || paymentDateDirty.value) return
  try {
    const response = await fetch('/api/calendar/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: maturity, currency: store.globalParams.deal_ccy || 'EUR', business_days: 3 }),
    })
    if (response.ok) {
      const proposed = (await response.json()).date
      if (!paymentDateDirty.value) setProposedPaymentDate(proposed)
      return
    }
  } catch { /* repli week-end uniquement ci-dessous */ }
  if (!paymentDateDirty.value) setProposedPaymentDate(addBizDays(maturity, 3))
}

function setProposedPaymentDate(date) {
  proposingPaymentDate = true
  store.globalParams.payment_date = date
  nextTick(() => { proposingPaymentDate = false })
}

watch(() => store.maturityDate, proposePaymentDate, { immediate: true })

function formatParamDefault(param) {
  const value = param.display_default
  if (Array.isArray(value)) return value.map(item => `${item}${param.is_pct ? '%' : ''}`).join(' · ')
  return `${value ?? '—'}${param.is_pct && value != null ? '%' : ''}`
}

const activeUIdx = computed(() => store.activeUnderlyingIdx)
const activeU = computed(() => store.underlyings[activeUIdx.value] ?? store.underlyings[0])

function onAddUnderlying() { store.addUnderlying() }
function onRemoveUnderlying() { store.removeUnderlying(activeUIdx.value) }
function onTickerSelect(ticker) {
  activeU.value.ticker = ticker
  if (ticker) store.loadYfOne(activeUIdx.value)
}

let tickerBeforeEdit = ''
function onTickerFocus() { tickerBeforeEdit = activeU.value.ticker }
function onTickerBlur() {
  activeU.value.ticker = activeU.value.ticker.trim().toUpperCase()
  if (activeU.value.ticker && activeU.value.ticker !== tickerBeforeEdit) store.loadYfOne(activeUIdx.value)
}

const tenor = value => (value?.value ? `${value.value}${value.unit}` : null)

function scheduleRequest(calendar) {
  const value = store.constatOverrides[calendar.name] || {}
  return {
    start_date: value.start_date,
    end_date: value.end_date,
    roll_date: value.roll_date,
    frequency: tenor(value.frequency),
    stub: value.stub,
    sub_frequency: tenor(value.sub_frequency),
    currency: store.globalParams.deal_ccy || 'EUR',
    convention: value.convention || 'none',
    settlement_lag: value.settlement_lag || 0,
  }
}

function samplingFrequency(calendar) {
  if (calendar.window_scope !== 'period') return null
  const value = store.constatOverrides[calendar.name]
  return tenor(value && typeof value === 'object' ? value.window_frequency : null)
}

const windowPreviews = reactive({})

function keepWindowPreview(name, response, payload, wrap) {
  if (response.ok) { windowPreviews[name] = wrap(payload); return }
  if (response.status === 422 && typeof payload?.detail === 'string') {
    windowPreviews[name] = { erreur: payload.detail }
  } else {
    delete windowPreviews[name]
  }
}

async function refreshWindowPreviews() {
  for (const calendar of store.scriptConstats) {
    const value = store.constatOverrides[calendar.name]
    if (!calendar.reduction || !value || typeof value !== 'object' || !value.window_frequency?.value) {
      delete windowPreviews[calendar.name]
      continue
    }
    const sampling = tenor(value.window_frequency)
    if (calendar.window_scope === 'period') {
      if (!(value.start_date && value.end_date && value.roll_date)) {
        delete windowPreviews[calendar.name]
        continue
      }
      try {
        const response = await fetch('/api/schedule/period-window', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            start_date: value.start_date, end_date: value.end_date, roll_date: value.roll_date,
            frequency: tenor(value.frequency), window_frequency: sampling,
            stub: value.stub || 'short_last', currency: store.globalParams.deal_ccy || null,
            convention: value.convention || 'none',
          }),
        })
        keepWindowPreview(calendar.name, response, await response.json(), payload => ({ periode: payload }))
      } catch { delete windowPreviews[calendar.name] }
      continue
    }
    if (!value.window_length?.value) { delete windowPreviews[calendar.name]; continue }
    const anchor = calendar.kind === 'single' ? value.date : value.end_date
    if (!anchor) { delete windowPreviews[calendar.name]; continue }
    try {
      const response = await fetch('/api/schedule/window', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date: anchor, window_length: tenor(value.window_length), window_frequency: sampling,
          forward: calendar.name === 'STRIKE_FIX', currency: store.globalParams.deal_ccy || null,
          convention: value.convention || 'none',
        }),
      })
      keepWindowPreview(calendar.name, response, await response.json(), payload => payload)
    } catch { delete windowPreviews[calendar.name] }
  }
}

let previewTimer = null
watch(() => [store.scriptConstats, store.constatOverrides, store.globalParams.deal_ccy], () => {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(refreshWindowPreviews, 350)
}, { deep: true, immediate: true })

const calendarDates = ref([])
const pastCloses = ref({})

async function loadCalendarDates() {
  const calendars = store.scriptConstats.filter(calendar => calendar.kind !== 'single')
  if (!calendars.length) { calendarDates.value = []; return }
  const dates = new Set()
  for (const calendar of calendars) {
    try {
      const response = await fetch('/api/schedule/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scheduleRequest(calendar)),
      })
      if (!response.ok) continue
      const payload = await response.json()
      ;(payload.dates || []).slice(1).forEach(date => dates.add(date))
    } catch { /* calendrier incomplet : repli sur les flux du pricing */ }
  }
  calendarDates.value = [...dates].sort()
}

const observationTimes = computed(() => {
  if (!store.result?.flux_table) return []
  return [...new Set(Object.values(store.result.flux_table).map(event => event.t))].sort((a, b) => a - b)
})

function addDays(isoDate, days) {
  const date = new Date(isoDate)
  date.setDate(date.getDate() + Math.round(days))
  return date.toISOString().split('T')[0]
}

const observationDates = computed(() => {
  if (calendarDates.value.length) return calendarDates.value
  const strike = store.globalParams.strike_date
  if (!strike) return []
  if (store.result?.in_life && store.result.valuation_date) {
    const past = [...new Set((store.result.past?.realized_flows || []).map(flow => flow.t))]
      .sort((a, b) => a - b).map(time => addDays(strike, time * 365.25))
    const future = observationTimes.value.map(time => addDays(store.result.valuation_date, time * 365.25))
    return [...past, ...future]
  }
  return observationTimes.value.map(time => addDays(strike, time * 365.25))
})

async function loadPastCloses() {
  const today = new Date().toISOString().split('T')[0]
  const days = new Set(observationDates.value)
  if (store.globalParams.strike_date) days.add(store.globalParams.strike_date)
  const pastDays = [...days].filter(day => day <= today).sort()
  const tickers = store.underlyings.map(underlying => underlying.ticker).filter(Boolean)
  if (!pastDays.length || !tickers.length) { pastCloses.value = {}; return }
  try {
    const query = new URLSearchParams({
      tickers: tickers.join(','),
      start: store.globalParams.strike_date || pastDays[0],
      end: today,
    })
    const response = await fetch(`/api/finance/hist_prices?${query}`)
    if (!response.ok) return
    const payload = await response.json()
    const result = {}
    for (const day of pastDays) {
      let index = -1
      for (let i = 0; i < (payload.dates || []).length; i += 1) {
        if (payload.dates[i] <= day) index = i
        else break
      }
      if (index < 0) continue
      result[day] = {}
      for (const ticker of tickers) {
        const series = payload.prices?.[ticker]
        if (series?.[index]) result[day][ticker] = series[index]
      }
    }
    pastCloses.value = result
  } catch { /* source indisponible : l'aperçu reste sans clôture */ }
}

watch(() => [store.scriptConstats, store.constatOverrides, store.globalParams.strike_date],
  loadCalendarDates, { deep: true, immediate: true })
watch(observationDates, loadPastCloses, { immediate: true })

const previewEvents = computed(() => {
  if (!observationDates.value.length && !store.result) return []
  const today = new Date().toISOString().split('T')[0]
  const strike = store.globalParams.strike_date || today
  const events = [{ label: 'Strike / Fixing S₀', date: strike, t: 0, isFuture: strike > today }]
  const dates = observationDates.value.length
    ? observationDates.value
    : observationTimes.value.map(time => addDays(strike, time * 365.25))
  dates.forEach((date, index) => {
    const time = Math.round(((new Date(date) - new Date(strike)) / 86400000 / 365.25) * 1e4) / 1e4
    events.push({
      label: index === dates.length - 1 ? 'Maturité' : `Obs. ${index + 1}`,
      date, t: time, isFuture: date > today,
    })
  })
  return events
})
</script>
