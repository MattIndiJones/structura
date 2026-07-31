<template>
  <div class="flex flex-col gap-5">

    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- MODE A — Deal booké sélectionné                                -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <template v-if="deal">

      <!-- Résumé du deal -->
      <div class="card">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <div class="text-slate-500 mb-0.5">Référence</div>
            <div class="font-mono font-semibold text-slate-200">{{ deal.reference }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Contrepartie</div>
            <div class="text-slate-200">{{ deal.contrepartie }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Nominal</div>
            <div class="font-mono text-slate-200">{{ formatNominal(deal.nominal) }} {{ deal.devise }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Prix / FV / Marge</div>
            <div class="font-mono">
              <span class="text-slate-200">{{ deal.price_traded.toFixed(2) }}%</span>
              <span class="text-slate-600 mx-1">/</span>
              <span class="text-slate-400">{{ deal.fair_value.toFixed(2) }}%</span>
              <span class="mx-1" :class="deal.margin >= 0 ? 'text-emerald-400' : 'text-red-400'">
                {{ deal.margin >= 0 ? '+' : '' }}{{ deal.margin.toFixed(2) }}%
              </span>
            </div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Trade date</div>
            <div class="font-mono text-slate-300">{{ formatDate(deal.trade_date) }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Strike date</div>
            <div class="font-mono text-slate-300">{{ formatDate(deal.strike_date) }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Value date</div>
            <div class="font-mono text-slate-300">{{ formatDate(deal.value_date) }}</div>
          </div>
          <div>
            <div class="text-slate-500 mb-0.5">Maturité</div>
            <div class="font-mono text-slate-300">{{ formatDate(deal.maturity_date) }}</div>
          </div>
        </div>

        <!-- S₀ — seulement si l'event strike (t=0) existe -->
        <template v-if="strikeEvent">
          <div v-if="hasS0" class="mt-3 pt-3 border-t border-slate-700">
            <div class="text-xs text-slate-500 mb-2">Spots initiaux S₀ (strike date)</div>
            <div class="flex flex-wrap gap-2">
              <div v-for="u in deal.underlyings" :key="u.name"
                class="flex items-center gap-1.5 bg-slate-800 rounded-lg px-3 py-1.5">
                <span class="text-xs text-slate-400 font-mono">{{ u.ticker || u.name }}</span>
                <span class="text-xs font-bold text-slate-200 font-mono">
                  {{ formatSpot(strikeEvent.spots[u.name]) }}
                </span>
              </div>
            </div>
          </div>
          <div v-else class="mt-3 pt-3 border-t border-slate-700">
            <p class="text-xs text-amber-500/80">
              S₀ à renseigner — saisissez les spots dans la 1ʳᵉ ligne (Strike / Fixing S₀) ci-dessous.
            </p>
          </div>
        </template>

        <!-- Statut + Re-pricer -->
        <div class="mt-3 flex items-center gap-2 flex-wrap">
          <span class="px-2 py-1 rounded border border-slate-700 bg-slate-800 text-xs text-slate-300">
            {{ deal.status }}
          </span>
          <HelpTip text="Le statut contractuel est en lecture seule. Un résultat terminal passe obligatoirement par proposition, validation humaine puis application auditée." />
          <button class="btn-secondary text-xs px-3 py-1.5" @click="reprice" :disabled="repricing">
            <span v-if="repricing"
              class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            ↺ Re-pricer
          </button>
          <HelpTip width="w-72" text="Recharge le script figé au booking dans le Pricer, avec la maturité restante (T remaining) et les spots normalisés (spot actuel / S₀) comme point de départ — pour obtenir une valorisation mark-to-market actuelle du deal. Vous atterrissez ensuite dans Marché &amp; Paramètres pour lancer le pricing." />
          <span v-if="repriceMsg" class="text-xs"
            :class="repriceMsg.startsWith('⚠') ? 'text-amber-400' : 'text-emerald-400'">
            {{ repriceMsg }}
          </span>
        </div>
      </div>

      <!-- Tableau des constatations (deal booké) -->
      <div class="card">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">
              Constatations ({{ deal.events?.length ?? 0 }})
            </h2>
            <p class="text-[10px] text-slate-600 mt-0.5">
              Sous-jacents figés au booking · {{ deal.underlyings.map(u => u.ticker || u.name).join(', ') }}
            </p>
          </div>
          <button class="btn-secondary text-xs px-3 py-1.5"
            :disabled="dealsStore.loading" @click="doRefresh">
            <span v-if="dealsStore.loading"
              class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
            📡 Actualiser monitoring indicatif
          </button>
        </div>

        <div v-if="deal.lifecycle_proposals?.length" class="mb-3 flex flex-col gap-2">
          <div v-for="proposal in deal.lifecycle_proposals" :key="proposal.id"
               class="rounded-lg border border-amber-800/50 bg-amber-950/20 px-3 py-2 flex items-center justify-between gap-3">
            <div class="text-xs">
              <span class="font-semibold text-amber-300">Résolution proposée : {{ proposal.proposed_outcome }}</span>
              <span class="ml-2 text-slate-500">{{ proposal.status }} · source {{ proposal.data_source }}</span>
              <div class="text-[10px] text-slate-500 mt-0.5">
                {{ proposal.result?.event_date || 'date inconnue' }} · aucune application automatique
              </div>
            </div>
            <div class="flex gap-2 shrink-0">
              <button v-if="proposal.status === 'PROPOSED'" class="btn-secondary text-xs px-2 py-1"
                      @click="validateProposal(proposal)">Valider</button>
              <button v-if="proposal.status === 'VALIDATED'" class="btn-primary text-xs px-2 py-1"
                      @click="applyProposal(proposal)">Appliquer</button>
            </div>
          </div>
        </div>

        <!-- Bandeau résultat refresh -->
        <div v-if="refreshBanner" class="mb-3 px-3 py-2.5 rounded-lg text-xs flex items-start gap-2"
          :class="refreshBanner.type === 'warn'
            ? 'bg-amber-950/50 border border-amber-800/50 text-amber-300'
            : refreshBanner.type === 'error'
              ? 'bg-red-950/50 border border-red-800/50 text-red-300'
              : 'bg-emerald-950/50 border border-emerald-800/50 text-emerald-300'">
          <span class="shrink-0">{{ refreshBanner.icon }}</span>
          <span>{{ refreshBanner.text }}</span>
        </div>

        <!-- Bandeau sauvegarde spot -->
        <div v-if="saveMsg" class="mb-3 px-3 py-2 rounded-lg text-xs bg-blue-950/40 border border-blue-800/50 text-blue-300">
          {{ saveMsg }}
        </div>

        <div class="overflow-x-auto table-shell" tabindex="0" role="region">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium pb-2 pr-3">#</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Label</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Date</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap num">T (Y)</th>
                <th v-for="u in deal.underlyings" :key="u.name"
                  class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">
                  {{ u.ticker || u.name }}
                  <span class="text-slate-600 font-normal ml-1">officiel / indicatif</span>
                </th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3">Fixing
                  <HelpTip text="Yahoo est uniquement indicatif. Un fixing officiel doit être saisi manuellement, complet, puis validé avant toute résolution." />
                </th>
                <th class="text-left text-slate-500 font-medium pb-2">Statut
                  <HelpTip text="futur = date pas encore atteinte. observé = spot constaté normalement. callé = ce constat a déclenché le rappel anticipé du produit. ki = barrière de knock-in franchie à ce constat. final = constat de maturité." />
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!deal.events?.length">
                <td :colspan="4 + (deal.underlyings?.length ?? 1) + 2"
                  class="py-6 text-center text-slate-600 italic text-xs">
                  Aucune constatation.
                </td>
              </tr>
              <tr v-for="ev in deal.events" :key="ev.id"
                :class="[
                  'border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors',
                  ev.t_years === 0 ? 'bg-amber-950/20' : '',
                  savingEventId === ev.id ? 'opacity-40' : '',
                  ev.event_date > today && ev.t_years !== 0 ? 'opacity-50' : '',
                ]">
                <td class="py-2 pr-3 text-slate-500">{{ ev.event_index + 1 }}</td>
                <td class="py-2 pr-3 whitespace-nowrap">
                  <span :class="ev.t_years === 0 ? 'text-amber-400 font-semibold' : 'text-slate-300'">
                    {{ ev.label }}
                  </span>
                </td>
                <td class="py-2 pr-3 font-mono text-slate-300 whitespace-nowrap">
                  {{ formatDate(ev.event_date) }}
                  <span v-if="ev.event_date === today" class="ml-1 text-amber-400 text-[10px]">aujourd'hui</span>
                </td>
                <td class="py-2 pr-3 font-mono num text-slate-400">{{ ev.t_years.toFixed(2) }}</td>
                <td v-for="u in deal.underlyings" :key="u.name" class="py-2 pr-3">
                  <div class="flex items-center gap-1.5">
                    <input :value="ev.spots[u.name] ?? ''"
                      @blur="patchSpot(ev, u.name, $event.target.value)"
                      type="number" step="any"
                      :disabled="['VALIDATED', 'APPLIED'].includes(ev.fixing_status)"
                      class="input w-24 text-xs py-0.5 font-mono"
                      :class="ev.spots[u.name] ? 'text-slate-200' : 'text-slate-600'"
                      placeholder="–" />
                    <span v-if="perf(ev, u)" class="text-[10px] font-mono shrink-0"
                      :class="perfClass(ev, u)">
                      {{ perf(ev, u) }}
                    </span>
                  </div>
                  <div v-if="ev.indicative_spots?.[u.name]" class="text-[10px] text-blue-400 mt-0.5 font-mono">
                    indic. {{ formatSpot(ev.indicative_spots[u.name]) }}
                  </div>
                </td>
                <td class="py-2 pr-3">
                  <span :class="sourceClass(ev.source)"
                    class="px-1.5 py-0.5 rounded text-[10px] font-medium">
                    {{ ev.fixing_status }}
                  </span>
                  <button v-if="['RECEIVED', 'PARTIAL', 'MANUAL_REVIEW_REQUIRED'].includes(ev.fixing_status)"
                          class="block mt-1 text-[10px] text-emerald-400 hover:text-emerald-300"
                          @click="validateEventFixing(ev)">Valider le fixing</button>
                </td>
                <td class="py-2">
                  <span class="text-[10px] bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-slate-300">
                    {{ ev.status }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-if="allEventsFuture && deal.events?.length" class="mt-3 text-[11px] text-slate-600 italic">
          Tous les événements sont futurs — saisissez les spots manuellement dans les cellules, ou
          cliquez "Actualiser spots Yahoo" après les dates de constatation.
        </p>
      </div>

    </template>

    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- MODE B — Preview live (aucun deal sélectionné)                 -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <template v-else>

      <!-- Pas encore de pricing -->
      <div v-if="!store.result" class="card">
        <p class="text-slate-500 text-sm text-center py-4">
          Lancez un pricing (▶ Pricer) pour visualiser la structure des constatations.
        </p>
      </div>

      <!-- Preview basée sur le pricing en cours -->
      <div v-else class="card">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h2 class="text-xs font-bold text-slate-400 uppercase tracking-wider">
              Structure des constatations
            </h2>
            <p class="text-[10px] text-slate-500 mt-0.5">
              Basée sur le pricing en cours · {{ store.underlyings.length }} sous-jacent(s) ·
              {{ previewEvents.length }} constatation(s)
            </p>
          </div>
          <button class="btn-primary text-xs px-3 py-1.5" @click="goToDeal">
            📋 Booker ce deal →
          </button>
        </div>

        <div class="overflow-x-auto table-shell" tabindex="0" role="region">
          <table class="w-full text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-700">
                <th class="text-left text-slate-500 font-medium pb-2 pr-3">#</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Label</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">Date indicative</th>
                <th class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap num">T (Y)</th>
                <th v-for="u in store.underlyings" :key="u.name"
                  class="text-left text-slate-500 font-medium pb-2 pr-3 whitespace-nowrap">
                  {{ u.ticker || u.name }}
                  <span class="text-slate-600 font-normal ml-1">S₀</span>
                </th>
                <th class="text-left text-slate-500 font-medium pb-2">Statut</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!previewEvents.length">
                <td :colspan="4 + store.underlyings.length + 1"
                  class="py-6 text-center text-slate-600 italic">
                  Aucune constatation détectée dans le script.
                </td>
              </tr>
              <tr v-for="(ev, i) in previewEvents" :key="i"
                :class="[
                  'border-b border-slate-800/50',
                  ev.t === 0 ? 'bg-amber-950/20' : 'opacity-60',
                ]">
                <td class="py-2 pr-3 text-slate-500">{{ i + 1 }}</td>
                <td class="py-2 pr-3 whitespace-nowrap"
                  :class="ev.t === 0 ? 'text-amber-400 font-semibold' : 'text-slate-300'">
                  {{ ev.label }}
                </td>
                <td class="py-2 pr-3 font-mono text-slate-400 whitespace-nowrap">{{ ev.date }}</td>
                <td class="py-2 pr-3 font-mono num text-slate-400">{{ ev.t.toFixed(2) }}</td>
                <td v-for="u in store.underlyings" :key="u.name" class="py-2 pr-3">
                  <span class="text-slate-700 font-mono text-[10px]">–</span>
                </td>
                <td class="py-2">
                  <span class="text-[10px] text-slate-600">futur</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p class="text-[10px] text-slate-600 mt-3 pt-3 border-t border-slate-800">
          Les spots S₀ et les dates exactes seront fixés au booking — cliquez "Booker ce deal →" pour
          verrouiller la structure.
        </p>
      </div>

    </template>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useDealsStore } from '../stores/deals.js'
import { usePricingStore } from '../stores/pricing.js'
import HelpTip from './HelpTip.vue'
import { formatDate } from '../utils/format.js'

const props = defineProps({ initialDealId: { type: Number, default: null } })

const dealsStore = useDealsStore()
const store = usePricingStore()

const today = new Date().toISOString().split('T')[0]
const repricing = ref(false)
const repriceMsg = ref('')
const savingEventId = ref(null)
const saveMsg = ref('')
let saveMsgTimer = null

const deal = computed(() => dealsStore.currentDeal)
const strikeEvent = computed(() => deal.value?.events?.find(e => e.t_years === 0) ?? null)
const hasS0 = computed(() => !!strikeEvent.value && Object.keys(strikeEvent.value.spots).length > 0)

const allEventsFuture = computed(() => {
  const evs = deal.value?.events
  if (!evs?.length) return false
  return evs.every(e => e.event_date > today)
})

// ── Preview live (avant booking) ──────────────────────────
function addDays(isoDate, days) {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + Math.round(days))
  return d.toISOString().split('T')[0]
}

const pricingObsTimes = computed(() => {
  if (!store.result?.flux_table) return []
  return [...new Set(Object.values(store.result.flux_table).map(e => e.t))].sort((a, b) => a - b)
})

const previewEvents = computed(() => {
  const base = store.globalParams.value_date || today
  const events = []

  events.push({
    label: 'Strike / Fixing S₀',
    date: addDays(base, -2),
    t: 0,
  })

  pricingObsTimes.value.forEach((t, idx) => {
    const isLast = idx === pricingObsTimes.value.length - 1
    events.push({
      label: isLast ? 'Maturité' : `Obs. ${idx + 1} (${t.toFixed(2)}Y)`,
      date: addDays(base, t * 365.25),
      t,
    })
  })

  return events
})

function goToDeal() {
  store.leftTab = 'deal'
}

// ── Lifecycle ─────────────────────────────────────────────
// Events is scoped to the product currently open in this Pricer session —
// not a picker across every deal ever booked (that's what /booking is for).
// It shows the real, frozen deal only if THIS script has already been
// booked; otherwise it falls back to the live indicative preview (Mode B).
onMounted(async () => {
  await dealsStore.loadDeals()
  const id = props.initialDealId
    ?? (store.currentScriptId
        ? dealsStore.deals.find(d => d.script_id === store.currentScriptId)?.id ?? null
        : null)
  if (id) await selectDeal(id)
})

async function selectDeal(id) {
  dealsStore.refreshStatus = ''
  await dealsStore.selectDeal(id)
}

// ── Formatting ────────────────────────────────────────────
function formatNominal(n) {
  return (n || 0).toLocaleString('fr-FR')
}

function formatSpot(s) {
  if (!s) return '–'
  return s.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
}

function s0ForUnderlying(name) {
  return strikeEvent.value?.spots?.[name] ?? 0
}

function perf(ev, u) {
  if (ev.t_years === 0) return null
  const s = ev.spots[u.name]
  const s0 = s0ForUnderlying(u.name)
  if (!s || !s0) return null
  const pct = ((s / s0 - 1) * 100).toFixed(1)
  return `${Number(pct) >= 0 ? '+' : ''}${pct}%`
}

function perfClass(ev, u) {
  const s = ev.spots[u.name], s0 = s0ForUnderlying(u.name)
  if (!s || !s0) return ''
  return s >= s0 ? 'text-emerald-400' : 'text-red-400'
}

function sourceClass(s) {
  if (s === 'auto') return 'bg-blue-900/40 text-blue-400'
  if (s === 'manuel') return 'bg-amber-900/40 text-amber-400'
  return 'bg-slate-700 text-slate-500'
}

// Bandeau refresh
const refreshBanner = computed(() => {
  const s = dealsStore.refreshStatus
  if (!s) return null
  if (s.startsWith('⚠')) return { type: 'error', icon: '⚠', text: s.slice(2).trim() }
  if (s.includes('0 événement')) {
    return {
      type: 'warn', icon: 'ℹ',
      text: 'Aucun événement passé à mettre à jour — les spots peuvent être saisis manuellement.',
    }
  }
  return { type: 'ok', icon: '✓', text: s.replace(/^[✓\s]+/, '') }
})

// ── Event edits ───────────────────────────────────────────
function showSaveMsg(text) {
  saveMsg.value = text
  clearTimeout(saveMsgTimer)
  saveMsgTimer = setTimeout(() => { saveMsg.value = '' }, 2500)
}

async function patchSpot(ev, underlyingName, rawVal) {
  const val = parseFloat(rawVal)
  if (isNaN(val) || val <= 0) return
  savingEventId.value = ev.id
  try {
    const spots = { ...ev.spots, [underlyingName]: val }
    await dealsStore.updateEvent(deal.value.id, ev.id, { spots, source: 'manuel' })
    showSaveMsg(`✓ Spot ${underlyingName} sauvegardé (${val.toLocaleString('fr-FR')})`)
  } catch (e) {
    showSaveMsg(`⚠ Erreur sauvegarde : ${e.message}`)
  } finally {
    savingEventId.value = null
  }
}

async function validateEventFixing(ev) {
  const reason = window.prompt('Motif de validation du fixing officiel :')
  if (!reason) return
  try {
    await dealsStore.validateFixing(deal.value.id, ev.id, reason)
    showSaveMsg('✓ Fixing officiel validé')
  } catch (e) {
    showSaveMsg(`⚠ Validation refusée : ${e.message}`)
  }
}

async function validateProposal(proposal) {
  const reason = window.prompt('Motif de validation de la résolution :')
  if (!reason) return
  try {
    await dealsStore.transitionProposal(
      deal.value.id, proposal.id, 'validate', reason, proposal.proposed_outcome)
    showSaveMsg('✓ Résolution validée, pas encore appliquée')
  } catch (e) {
    showSaveMsg(`⚠ Validation refusée : ${e.message}`)
  }
}

async function applyProposal(proposal) {
  const reason = window.prompt('Motif d’application définitive de la résolution :')
  if (!reason) return
  try {
    await dealsStore.transitionProposal(deal.value.id, proposal.id, 'apply', reason)
    showSaveMsg('✓ Résolution appliquée')
  } catch (e) {
    showSaveMsg(`⚠ Application refusée : ${e.message}`)
  }
}

async function doRefresh() {
  if (!deal.value) return
  dealsStore.refreshStatus = ''
  try {
    await dealsStore.refreshEvents(deal.value.id)
  } catch { /* error already in refreshStatus */ }
}

// ── Re-pricer ─────────────────────────────────────────────
async function reprice() {
  if (!deal.value) return
  repricing.value = true; repriceMsg.value = ''
  try {
    const inputs = await dealsStore.getRepriceInputs(deal.value.id)

    // Deal already resolved (callé/échu) — no optionality left to run a
    // Monte Carlo on. Re-simulating from today on the raw script would
    // price it as if it restarted now (AT 1,2,3 means "1/2/3Y from now" to
    // the engine, not from the original inception). Show what was actually
    // realized instead.
    if (inputs.resolved) {
      const payout = inputs.realized_payout != null ? `${(inputs.realized_payout * 100).toFixed(2)}%` : 'inconnu'
      repriceMsg.value = `Prix résiduel : 0% (deal clos) · Remboursement réalisé : ${payout}` +
        (inputs.resolution_date ? ` le ${inputs.resolution_date}` : '')
      return
    }

    store.script = inputs.script_snapshot
    await store.parseScript()
    store.globalParams.T = inputs.T_remaining
    store.globalParams.value_date = deal.value.value_date
    if (inputs.underlyings?.length) {
      store.underlyings = inputs.underlyings.map(u => ({ ...u }))
      store.activeUnderlyingIdx = 0
    }
    if (inputs.corr_matrix?.length) store.corrMatrix = inputs.corr_matrix
    const ms = inputs.market_snapshot || {}
    if (ms.model) store.globalParams.model = ms.model
    if (ms.r != null) store.globalParams.r = ms.r
    const parts = [`T restant: ${inputs.T_remaining.toFixed(2)}Y`]
    const ns = inputs.normalized_spots || {}
    if (Object.keys(ns).length) {
      parts.push(`Spot/S₀: ${Object.entries(ns).map(([n, v]) => `${n}: ${(v * 100).toFixed(1)}%`).join(', ')}`)
    }
    repriceMsg.value = parts.join(' · ')
    store.leftTab = 'params'
  } catch (e) {
    repriceMsg.value = `⚠ ${e.message}`
  } finally {
    repricing.value = false
  }
}
</script>
