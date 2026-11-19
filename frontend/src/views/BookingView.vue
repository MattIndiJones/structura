<template>
  <div class="flex-1 flex flex-col min-h-0 text-slate-100">

    <main class="flex-1 overflow-y-auto p-6">
      <div class="max-w-[1600px] mx-auto flex flex-col gap-3">

        <div class="page-header">
          <div class="flex items-center gap-3">
            <BackLink :fallback="{ path: '/', query: { category: 'life_cycle' } }" />
            <h1 class="page-title">Booking — produits bookés</h1>
          </div>
          <div class="page-actions">
            <span v-if="refreshBookStatus" class="text-xs" style="color: var(--muted);">{{ refreshBookStatus }}</span>
            <button class="btn-secondary text-xs px-3 py-1.5" :disabled="refreshingBook || authStore.readOnly" @click="refreshBook">
              {{ refreshingBook ? '⏳ Rafraîchissement…' : '🔄 Rafraîchir le book' }}
            </button>
            <span v-if="dealsStore.deals.length" class="text-xs" style="color: var(--muted);">
              {{ filteredDeals.length }} / {{ dealsStore.deals.length }} deal(s)
            </span>
          </div>
        </div>

        <LifecycleRefreshSummary v-if="refreshBookSummary" :summary="refreshBookSummary" />

        <LoadingSpinner v-if="dealsStore.loading && !dealsStore.deals.length" class="py-10" />

        <EmptyState v-else-if="!dealsStore.deals.length" icon="📒" title="Aucun deal booké pour l'instant"
          hint="Un deal se book depuis l'onglet Deal du Pricer, une fois un pricing lancé." />

        <template v-else>

          <!-- ── Alertes non lues et statistiques du book filtré ── -->
          <BookingOverview />

          <!-- ── Barre d'onglets ────────────────────────────────── -->
          <div class="flex border-b border-slate-800 -mb-1">
            <button @click="activeTab = 'watchlist'"
              :class="activeTab === 'watchlist' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
              class="px-5 py-2.5 text-sm font-medium transition-colors">
              Surveillance
            </button>
            <button @click="activeTab = 'deals'"
              :class="activeTab === 'deals' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
              class="px-5 py-2.5 text-sm font-medium transition-colors">
              Deals ({{ filteredDeals.length }})
            </button>
            <RouterLink to="/risk"
              class="ml-auto self-center text-xs text-slate-500 hover:text-slate-300 transition-colors px-3"
              title="Portefeuilles, Greeks agrégés, chocs et P&L explain ont déménagé dans le module Risk Management">
              Portefeuilles &amp; chocs → Risk Management ↗
            </RouterLink>
          </div>

          <div v-if="commercialScope.active && activeTab === 'watchlist'"
               class="flex items-center justify-between gap-3 rounded-lg border border-blue-800/50 bg-blue-950/20 px-3 py-2 text-xs">
            <div>
              <span class="font-semibold text-blue-300">Surveillance filtrée</span>
              <span class="text-slate-400"> · {{ commercialScope.label }}</span>
              <span class="text-slate-600"> — mêmes événements et statuts que le Life Cycle.</span>
            </div>
            <RouterLink to="/booking" class="text-blue-400 hover:text-blue-300 whitespace-nowrap">
              Afficher tout
            </RouterLink>
          </div>

          <!-- ── Onglet Surveillance : watchlist barrières ──────── -->
          <template v-if="activeTab === 'watchlist'">
            <BookingWatchlistTab />
          </template><!-- /watchlist tab -->

          <!-- ── Onglet Deals : filtres + liste ────────────────── -->
          <template v-if="activeTab === 'deals'">

          <!-- ── Filtres ─────────────────────────────────────────── -->
          <BookingDealFilters />

          <!-- ── Liste des deals ──────────────────────────────── -->
          <div v-if="!filteredDeals.length" class="card text-sm text-slate-500">
            Aucun deal ne correspond à ces filtres.
          </div>

          <div v-for="(d, dealIndex) in filteredDeals" :key="d.id" :id="`deal-${d.id}`"
            class="card deal-card flex flex-col gap-3 hover:shadow-xl hover:shadow-black/30
                   hover:border-slate-700 transition-all duration-200 scroll-mt-4"
            :class="{ 'deal-card--alternate': dealIndex % 2 === 1 }">
            <!-- Ligne d'en-tête — cliquable pour déplier la fiche détail -->
            <DealCardHeader :d="d" />

            <DealOverview :d="d" />

            <DealActionResults :d="d" />

            <DealDetail :d="d" />
          </div>

          </template><!-- /deals tab -->



        </template>
      </div>
    </main>

    <AutoFixingExceptionModal
      v-model="autoExceptionModal.open"
      :deal="autoExceptionModal.deal"
      :event="autoExceptionModal.event"
      @resolved="onAutoExceptionResolved" />
  </div>
</template>

<script setup>
import BookingOverview from './booking/BookingOverview.vue'
import BookingWatchlistTab from './booking/BookingWatchlistTab.vue'
import BookingDealFilters from './booking/BookingDealFilters.vue'
import DealCardHeader from './booking/DealCardHeader.vue'
import DealOverview from './booking/DealOverview.vue'
import DealActionResults from './booking/DealActionResults.vue'
import DealDetail from './booking/DealDetail.vue'
import { BOOKING_CONTEXT } from './booking/context.js'
import { bookedGrid } from '../utils/simulationGrid.js'

import BackLink from '../components/ui/BackLink.vue'
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch, provide } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useDealsStore } from '../stores/deals.js'
import { usePortfoliosStore, shockPresets, blankShockForm } from '../stores/portfolios.js'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch, apiErrorMessage } from '../utils/api.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import AutoFixingExceptionModal from '../components/AutoFixingExceptionModal.vue'
import { useBookingMtm, localDay } from '../composables/useBookingMtm.js'
import { useDataFilter } from '../composables/useDataFilter.js'
import { formatInt } from '../utils/format.js'
import LifecycleRefreshSummary from '../components/LifecycleRefreshSummary.vue'
import { estReleve } from '../utils/dealEvents.js'
import {
  _STATUS_ORDER, autoExceptionStatuses, barrierBusinessLabel, datePct, dealPayoffFamily,
  describeOutcome, formatGaugeLevel, modelBusinessLabel, pct, queryId, wlColumns, wlFilterFields,
} from './booking/dealLabels.js'

const route = useRoute()
const dealsStore = useDealsStore()
const portfoliosStore = usePortfoliosStore()
const authStore = useAuthStore()

// Portfolio list & deal→portfolio assignment live in the shared store (the
// Risk Management module is the primary owner) — Booking only reads the list
// for its filter/assignment dropdowns.
const portfolios = computed(() => portfoliosStore.portfolios)
const shockHistory = portfoliosStore.shockHistory
const portfolioAssigning = reactive({})
const portfolioAssignmentStatus = reactive({})

function dealPortfolioLabel(deal) {
  const ids = deal.portfolio_ids || []
  if (!ids.length) return 'Non classé'
  if (ids.length === 1) return portfolios.value.find(p => p.id === ids[0])?.name || '1 portefeuille'
  return `${ids.length} portefeuilles`
}

async function toggleDealPortfolio(deal, portfolioId, checked) {
  if (portfolioAssigning[deal.id]) return
  const target = portfolios.value.find(p => p.id === portfolioId)
  const currentIds = deal.portfolio_ids || []
  const nextIds = checked
    ? [...new Set([...currentIds, portfolioId])]
    : currentIds.filter(id => id !== portfolioId)
  portfolioAssigning[deal.id] = true
  portfolioAssignmentStatus[deal.id] = ''
  try {
    await portfoliosStore.setDealPortfolios(deal.id, nextIds)
    portfolioAssignmentStatus[deal.id] = checked
      ? `✓ Ajouté à ${target?.name || 'portefeuille'}`
      : `✓ Retiré de ${target?.name || 'portefeuille'}`
  } catch (e) {
    portfolioAssignmentStatus[deal.id] = `⚠ ${e.message}`
  } finally {
    portfolioAssigning[deal.id] = false
  }
}

function canAssignPortfolio(deal) {
  return authStore.canAdministerOrganization || deal.user_id === authStore.user?.id
}

function portfoliosForDeal(deal) {
  return portfolios.value.filter(p => p.user_id === deal.user_id)
}

const activeTab = ref('watchlist')

const refreshingId = ref(null)
const refreshResults = reactive({})
const copiedReference = ref('')
let copyReferenceTimer = null

async function copyDealReference(reference) {
  try {
    await navigator.clipboard.writeText(reference)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = reference
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  }
  copiedReference.value = reference
  clearTimeout(copyReferenceTimer)
  copyReferenceTimer = setTimeout(() => {
    copiedReference.value = ''
  }, 1800)
}

// ── Fiche détail dépliable (accordéon multi-ouvert) ─────────────────
const expanded = reactive({})
const details = reactive({})   // deal_id → full deal (with events)
const detailErrors = reactive({})
const detailRevisions = {}
const autoExceptionModal = reactive({ open: false, deal: null, event: null })

function canResolveAutoException(deal, event) {
  return deal?.fixing_policy === 'AUTO_YAHOO' &&
    event?.event_date <= todayIso.value && autoExceptionStatuses.has(event?.fixing_status)
}

function autoExceptionEvents(dealId) {
  const fullDeal = details[dealId]
  return (fullDeal?.events || []).filter(event =>
    canResolveAutoException(fullDeal, event))
}

function openAutoException(deal, event) {
  autoExceptionModal.deal = details[deal.id] || deal
  autoExceptionModal.event = event
  autoExceptionModal.open = true
}

async function onAutoExceptionResolved(result) {
  const dealId = autoExceptionModal.deal?.id
  if (!dealId) return
  refreshResults[dealId] = `✓ ${result.message}`
  await loadDetail(dealId)
  await dealsStore.loadDeals()
  loadAlerts()
  loadWatchlist()
  const remaining = autoExceptionEvents(dealId)
  if (remaining.length) {
    autoExceptionModal.deal = details[dealId]
    autoExceptionModal.event = remaining[0]
  } else {
    autoExceptionModal.open = false
    autoExceptionModal.deal = null
    autoExceptionModal.event = null
  }
}

async function toggleDetail(id) {
  const opening = !expanded[id]
  expanded[id] = opening
  if (!opening) return
  if (!details[id]) await loadDetail(id)
  await loadSavedMtm(id)
  await focusDealCard(id)
}

async function focusDealCard(id) {
  await nextTick()
  await new Promise(resolve => window.requestAnimationFrame(resolve))
  const card = document.getElementById(`deal-${id}`)
  if (!card) return
  const scrollContainer = card.closest('main')
  const availableHeight = (scrollContainer?.clientHeight || window.innerHeight) - 48
  card.scrollIntoView({
    behavior: 'smooth',
    block: card.offsetHeight <= availableHeight ? 'center' : 'start',
  })
}

async function loadDetail(id) {
  const revision = detailRevisions[id] = (detailRevisions[id] || 0) + 1
  delete detailErrors[id]
  try {
    const res = await apiFetch(`/api/deals/${id}`)
    const data = await res.json()
    if (!res.ok) throw new Error(apiErrorMessage(data, 'Détail du deal indisponible. Réessayez.'))
    if (detailRevisions[id] === revision) details[id] = data
  } catch (error) {
    if (detailRevisions[id] === revision) detailErrors[id] = error.message || 'Détail du deal indisponible. Réessayez.'
  }
}

function lifePct(d) {
  // Resolved deals: life effectively ended at the resolving event.
  if (d.status !== 'actif') {
    const evs = details[d.id]?.events || []
    const resolving = evs.find(e => ['callé', 'ki', 'final'].includes(e.status))
    if (resolving) return Math.round(datePct(d, resolving.event_date) ?? 100)
    return 100
  }
  const p = datePct(d, todayIso.value)
  return p === null ? null : Math.round(p)
}

function obsEvents(id) {
  // Les relevés ne sont pas des constatations : pas de point sur la frise.
  return (details[id]?.events || []).filter(e => e.t_years > 0 && !estReleve(e))
}

function operationalEventLabel(ev) {
  if (ev.event_date > todayIso.value) return 'À venir'
  if (ev.fixing_status === 'EXPECTED') return 'À récupérer'
  if (ev.fixing_status === 'RECEIVED') return 'Exception à traiter'
  if (['PARTIAL', 'MISSING', 'REJECTED', 'CONTESTED', 'MANUAL_REVIEW_REQUIRED'].includes(ev.fixing_status)) {
    return 'Exception à traiter'
  }
  return ev.status === 'futur' ? 'Fixing à appliquer' : ev.status
}

function s0For(id, name) {
  const strike = (details[id]?.events || []).find(e => e.t_years === 0)
  return strike?.spots?.[name] ?? null
}

// Which level the ruler reads — see build_watchlist_row:_observable_value.
function gaugeObservableLabel(deal, observable) {
  const rows = wlRow(deal.id)?.underlyings || []
  const tickerOf = (u) => u?.ticker || u?.name || ''
  const single = rows.length === 1 ? tickerOf(rows[0]) : ''
  const priced = rows.filter(u => u.perf != null)
  const extreme = (pick) => priced.length
    ? tickerOf(priced.reduce((a, b) => (pick(b.perf, a.perf) ? b : a)))
    : ''

  if (observable === 'WOF') {
    const worst = extreme((x, y) => x < y)
    return single || (worst ? `Worst-of · ${worst}` : 'Worst-of')
  }
  if (observable === 'BOF') {
    const best = extreme((x, y) => x > y)
    return single || (best ? `Best-of · ${best}` : 'Best-of')
  }
  if (observable === 'WOF_MIN') return `${single || 'Worst-of'} · plus bas depuis le strike`
  if (observable === 'BOF_MAX') return `${single || 'Best-of'} · plus haut depuis le strike`
  if (observable === 'BASKET') return 'Panier'
  const indexed = /^S(?:_MIN|_MAX)?\[(\d+)\]$/.exec(observable || '')
  if (indexed) return tickerOf(rows[Number(indexed[1]) - 1]) || observable
  return observable
}

function gaugeAriaLabel(deal, gauge) {
  const marks = gauge.marks.map(m => `${barrierBusinessLabel(m)} ${formatGaugeLevel(m.level)}`)
  return `${gaugeObservableLabel(deal, gauge.observable)} à ${formatGaugeLevel(gauge.current)} du strike — ${marks.join(', ')}`
}

// Watchlist join — live spot/perf and barrier gaps for active deals
function wlRow(id) {
  return watchlist.value.find(w => w.deal_id === id) || null
}

function wlUnderlying(id, name) {
  return wlRow(id)?.underlyings?.find(u => u.name === name) || null
}

function strikeFor(id, name) {
  return s0For(id, name) ?? wlUnderlying(id, name)?.s0 ?? null
}

// ── Alertes cycle de vie / barrières ────────────────────────────────
const alerts = ref([])
const alertError=ref(''),markingAll=ref(false),markingAlerts=reactive(new Set())
let alertsRevision=0
const refreshingBook = ref(false)
const refreshBookStatus = ref('')
const refreshBookSummary = ref(null)

async function loadAlerts() {
  const revision=++alertsRevision
  try {
    const res = await apiFetch('/api/alerts?unread_only=true')
    if (res.ok) {const data=await res.json();if(revision===alertsRevision) alerts.value=data.alerts}
  } catch { /* non bloquant — la page reste utilisable sans alertes */ }
}

async function markRead(a) {
  if(markingAll.value || markingAlerts.has(a.id)) return
  markingAlerts.add(a.id);alertError.value=''
  try {
    const response=await apiFetch(`/api/alerts/${a.id}/read`, { method: 'POST' })
    if(!response.ok) throw Error(apiErrorMessage(await response.json().catch(()=>({})),'Acquittement refusé.'))
    alertsRevision++
    alerts.value = alerts.value.filter(x => x.id !== a.id)
  } catch(e) {alertError.value=e.message}
  finally {markingAlerts.delete(a.id)}
}

async function markAllRead() {
  if(markingAll.value || markingAlerts.size) return
  const ids=new Set(alerts.value.map(a=>a.id))
  markingAll.value=true;alertError.value=''
  try {
    const response=await apiFetch('/api/alerts/read-all', { method: 'POST' })
    if(!response.ok) throw Error(apiErrorMessage(await response.json().catch(()=>({})),'Acquittement global refusé.'))
    alertsRevision++
    alerts.value=alerts.value.filter(a=>!ids.has(a.id))
  } catch(e) {alertError.value=e.message}
  finally {markingAll.value=false}
}

async function refreshBook() {
  if (refreshingBook.value || authStore.readOnly) return
  refreshingBook.value = true; refreshBookStatus.value = ''; refreshBookSummary.value = null
  try {
    const res = await apiFetch('/api/alerts/refresh-book', { method: 'POST' })
    if (!res.ok) throw new Error((await res.json()).detail || 'Erreur refresh')
    const s = await res.json()
    refreshBookSummary.value = s
    await dealsStore.loadDeals()
    const ids = dealsStore.deals.map(deal => deal.id)
    ids.forEach(invalidateMtm)
    await Promise.all([loadWatchlist(), loadAlerts(), ...ids.filter(id => expanded[id]).map(loadDetail)])
  } catch (e) {
    refreshBookStatus.value = `⚠ ${e.message}`
  } finally {
    refreshingBook.value = false
  }
}

// ── MtM résiduel ────────────────────────────────────────────────────
const {
  todayIso, mtmLoading, mtmResults, mtmModeFor, mtmDateFor, setMtmMode, setMtmDate,
  loadSavedMtms, loadSavedMtm, runMtm, mtmProgressLabel, syncDay, invalidateMtm,
  mtmGridFor, mtmGridChoiceFor, setMtmGrid,
} = useBookingMtm(() => authStore.readOnly ? authStore.user.consultation.date : localDay(), { archived: authStore.readOnly, bookedGrid: id => bookedGrid(dealsStore.deals.find(deal => deal.id === id)?.market_snapshot) })
let dayTimer
function refreshDay() {
  syncDay()
  clearTimeout(dayTimer)
  if (authStore.readOnly) return
  const now = new Date()
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
  dayTimer = setTimeout(refreshDay, midnight - now + 50)
}

function mtmResultDate(id) {
  const result = mtmResults[id]
  return result?.valuation_date
    || result?.market_used?.data?.contractual_history?.requested_end
    || mtmDateFor(id)
}

function repricingModelLabel(deal) {
  if (mtmModeFor(deal.id) === 'realized') return 'GBM'
  return modelBusinessLabel(mtmResults[deal.id]?.market_used?.model || deal.market_snapshot?.model)
}

function effectiveRateLabel(deal) {
  const used = mtmResults[deal.id]?.market_used
  const rate = used?.r ?? deal.market_snapshot?.r
  if (rate == null) return 'Non renseigné'
  return `${Number(rate).toFixed(2)}%${used?.r_is_default ? ' (défaut)' : ''}`
}

function effectiveFundingLabel(deal) {
  const used = mtmResults[deal.id]?.market_used
  if (used?.funding_curve?.length) return `Courbe · ${used.funding_curve.length} piliers`
  if (used?.funding_spread != null) return `${Number(used.funding_spread).toFixed(2)}%`

  const market = deal.market_snapshot || {}
  if (market.funding_curve?.length) return `Courbe · ${market.funding_curve.length} piliers`
  if (market.funding?.mode === 'pillars' && market.funding.pillars?.length) {
    return `Courbe · ${market.funding.pillars.length} piliers`
  }
  if (market.funding?.level != null) return `${Number(market.funding.level).toFixed(2)}%`
  return `${(Number(market.funding_spread || 0) * 100).toFixed(2)}%`
}

function effectiveProviderLabel(deal) {
  const provider = mtmResults[deal.id]?.market_used?.data?.provider || deal.market_data_provider
  if (provider === 'YAHOO_FINANCE' || provider === 'YAHOO') return 'Yahoo Finance'
  return provider || 'Yahoo Finance'
}

// ── Greeks (bump-and-reprice CRN) ────────────────────────────────────
const greeksLoading = reactive({})
const greeksResults = reactive({})

// Falls back to the deal's persisted last computation (greeks/greeks_computed_at,
// set by a previous call to POST .../greeks) until a fresh one is fetched in
// this session — the button only refreshes it, the row isn't blank on load.
function greeksFor(d) {
  if (greeksResults[d.id]) return greeksResults[d.id]
  if (d.greeks_computed_at) return { ...d.greeks, computed_at: d.greeks_computed_at }
  return null
}

async function runGreeks(id) {
  greeksLoading[id] = true
  greeksResults[id] = null
  try {
    const mode = mtmModeFor(id)
    const res = await apiFetch(`/api/deals/${id}/greeks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        recalibrate: mode === 'realized' ? 'realized' : 'none',
        valuation_date: mtmDateFor(id),
        steps_per_year: mtmGridFor(id),
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur Greeks')
    greeksResults[id] = data
  } catch (e) {
    greeksResults[id] = { error: e.message }
  } finally {
    greeksLoading[id] = false
  }
}

// ── Choc de marché (deal seul) ───────────────────────────────────────
// Presets, history and the shock runner live in the shared portfolios store
// (also used by Risk Management's Chocs tab) — only the per-deal panel UI
// state stays here.
const shockPanelOpen = reactive({})
const shockForm = reactive({})
const shockLoading = reactive({})
const shockResults = reactive({})

function applyShockPreset(id, label) {
  const preset = shockPresets.find(p => p.label === label)
  if (!preset) return
  shockForm[id] = { spot_shock_pct: preset.spot_shock_pct, vol_shock_pts: preset.vol_shock_pts,
                    rate_shock_bp: preset.rate_shock_bp, corr_shock_pts: preset.corr_shock_pts }
}

async function toggleShockPanel(id) {
  shockPanelOpen[id] = !shockPanelOpen[id]
  if (shockPanelOpen[id]) {
    if (!shockForm[id]) shockForm[id] = blankShockForm()
    await portfoliosStore.loadShockHistory('deal', id)
  }
}

async function runDealShock(id) {
  shockLoading[id] = true
  shockResults[id] = null
  try {
    shockResults[id] = await portfoliosStore.runShock('deal', id, shockForm[id])
  } catch (e) {
    shockResults[id] = { error: e.message }
  } finally {
    shockLoading[id] = false
  }
}

// P&L explain between two dates — time/state, spot, dividend, vol and corr (see
// EXPLICATION_VALO_DESIGN.md). Date 1 defaults to booking, date 2 to today.
const explainD1 = reactive({})
const explainD2 = reactive({})
const explainLoading = reactive({})
const explainResults = reactive({})
function defaultExplainStart(d) {
  // Value date is the normal P&L origin. For a freshly-booked deal whose
  // settlement is still in the future, use the trade date (or strike as a
  // final fallback) so the screen never proposes a future-to-past period.
  return [d.value_date, d.trade_date, d.strike_date]
    .find(value => value && value <= todayIso.value) || todayIso.value
}

function explainDatesValid(d) {
  const date1 = explainD1[d.id] || defaultExplainStart(d)
  const date2 = explainD2[d.id] || todayIso.value
  return !!date1 && !!date2 && date1 <= date2 && date2 <= todayIso.value
}

async function runExplain(d) {
  explainLoading[d.id] = true
  explainResults[d.id] = null
  try {
    const res = await apiFetch(`/api/deals/${d.id}/mtm/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date1: explainD1[d.id] || defaultExplainStart(d),
        date2: explainD2[d.id] || todayIso.value,
        recalibrate: mtmModeFor(d.id) === 'realized' ? 'realized' : 'none',
        steps_per_year: mtmGridFor(d.id),
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur explication')
    explainResults[d.id] = data
  } catch (e) {
    explainResults[d.id] = { error: e.message }
  } finally {
    explainLoading[d.id] = false
  }
}

const explainNoteLoading = reactive({})

async function downloadExplainNote(d) {
  const selected = explainResults[d.id]?.archive_id
  if (!selected) return
  explainNoteLoading[d.id] = true
  try {
    const res = await apiFetch(`/api/deals/${d.id}/mtm/explain/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        archive_id: selected,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Erreur génération PDF')
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Explication_valo_${d.reference}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    refreshResults[d.id] = `⚠ Note d'explication : ${e.message}`
  } finally {
    explainNoteLoading[d.id] = false
  }
}

// Flow A (module réinvestissement) — reconduire le même produit sur le même
// sous-jacent, départ forward (value date = aujourd'hui, tenor plein). Juste
// un pricing de comparaison, rien n'est booké tant que Philippe ne le décide
// pas explicitement. Voir MEMORY investment-solution-module.
const rollLoading = reactive({})
const rollResults = reactive({})

async function runRoll(d) {
  rollLoading[d.id] = true
  rollResults[d.id] = null
  try {
    const res = await apiFetch(`/api/deals/${d.id}/reinvest/roll`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur reconduction')
    rollResults[d.id] = data
  } catch (e) {
    rollResults[d.id] = { error: e.message }
  } finally {
    rollLoading[d.id] = false
  }
}

const watchlist = ref([])
const watchlistError = ref('')
const watchlistLoading = ref(false)

const commercialClientId = computed(() => queryId(route.query.client_id))
const commercialMandateId = computed(() => queryId(route.query.mandate_id))
const commercialScope = computed(() => {
  const clientId = commercialClientId.value
  const mandateId = commercialMandateId.value
  if (!clientId && !mandateId) return { active: false, label: '' }

  const matchingDeal = dealsStore.deals.find(deal =>
    (!clientId || deal.client_id === clientId)
    && (!mandateId || deal.mandate_id === mandateId))
  const snapshot = matchingDeal?.client_attribution_current
    || matchingDeal?.client_provenance
    || {}
  const clientLabel = snapshot.client?.name || (clientId ? `Client #${clientId}` : null)
  const mandateLabel = snapshot.mandate?.name || (mandateId ? `Mandat #${mandateId}` : null)
  return {
    active: true,
    label: [clientLabel, mandateLabel].filter(Boolean).join(' · '),
  }
})

async function loadWatchlist() {
  watchlistError.value = ''
  watchlistLoading.value = true
  try {
    watchlist.value = await dealsStore.getWatchlist({
      clientId: commercialClientId.value,
      mandateId: commercialMandateId.value,
    })
  } catch (e) {
    watchlistError.value = e.message
  } finally {
    watchlistLoading.value = false
  }
}

watch(
  () => [route.query.client_id, route.query.mandate_id],
  () => loadWatchlist(),
)

// Default watchlist order = next observation soonest first (backend sorts by
// barrier urgency instead — kept for the daily alert scan, not for this view).
const watchlistByUrgency = computed(() =>
  [...watchlist.value].sort((a, b) =>
    (a.days_to_next ?? Infinity) - (b.days_to_next ?? Infinity)
  )
)

const wlSorts = wlColumns
const wlFilter = useDataFilter(watchlistByUrgency, wlFilterFields, {
  sorts: wlSorts, defaultSort: 'days_to_next',
})

function sortWatchlistBy(key) {
  if (wlFilter.sortBy.value === key) wlFilter.toggleSortDir()
  else {
    wlFilter.sortBy.value = key
    wlFilter.sortDir.value = 'asc'
  }
}

function watchlistSortTitle(column) {
  const descending = wlFilter.sortBy.value === column.key && wlFilter.sortDir.value === 'asc'
  const numeric = ['days_to_next', 'wof', 'min_gap'].includes(column.key)
  const direction = numeric
    ? (descending ? 'décroissant' : 'croissant')
    : (descending ? 'alphabétique Z à A' : 'alphabétique A à Z')
  return `${column.label} : trier par ordre ${direction}`
}
const sortedWatchlist = computed(() => wlFilter.filtered.value)

// Reference click in the watchlist → jump to the deal's own card in the
// Deals tab (expanded + scrolled into view), as an alternative to opening it
// in the Pricer (the ⇥ icon next to it).
async function openDealDetail(id) {
  if (!filteredDeals.value.some(deal => deal.id === id)) resetFilters()
  activeTab.value = 'deals'
  expanded[id] = true
  if (!details[id]) await loadDetail(id)
  await loadSavedMtm(id)
  await focusDealCard(id)
}

// Vue Router keeps Booking mounted when only ?deal= changes.
watch(() => route.query.deal, value => {
  const id = Number(value)
  if (Number.isSafeInteger(id) && id > 0) openDealDetail(id)
})

const sortBy  = ref('status')
const sortDir = ref('asc')
function toggleSortDir() { sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc' }

const filters = reactive({
  contrepartie: '',
  ticker: '',
  productType: '',
  payoffFamily: '',
  status: '',
  portfolioId: '',
})

const hasActiveFilters = computed(() =>
  !!(filters.contrepartie || filters.ticker || filters.productType || filters.payoffFamily || filters.status || filters.portfolioId)
)

function resetFilters() {
  filters.contrepartie = ''
  filters.ticker = ''
  filters.productType = ''
  filters.payoffFamily = ''
  filters.status = ''
  filters.portfolioId = ''
}

const tickerOptions = computed(() => {
  const set = new Set()
  for (const d of dealsStore.deals) {
    for (const u of d.underlyings || []) {
      if (u.ticker) set.add(u.ticker)
    }
  }
  return [...set].sort()
})

const productTypeOptions = computed(() => {
  const set = new Set()
  for (const d of dealsStore.deals) {
    if (d.product_type) set.add(d.product_type)
  }
  return [...set].sort()
})

const payoffFamilyOptions = computed(() => {
  const labels = new Set(dealsStore.deals.map(dealPayoffFamily).filter(Boolean))
  return [...labels].sort((a, b) => a.localeCompare(b, 'fr'))
})

const filteredDeals = computed(() => {
  const list = dealsStore.deals.filter(d => {
    if (filters.status && d.status !== filters.status) return false
    if (filters.productType && d.product_type !== filters.productType) return false
    if (filters.payoffFamily && dealPayoffFamily(d) !== filters.payoffFamily) return false
    if (filters.contrepartie && !d.contrepartie.toLowerCase().includes(filters.contrepartie.toLowerCase())) return false
    if (filters.ticker && !(d.underlyings || []).some(u => u.ticker === filters.ticker)) return false
    if (filters.portfolioId && !(d.portfolio_ids || []).map(String).includes(filters.portfolioId)) return false
    return true
  })
  return [...list].sort((a, b) => {
    let cmp = 0
    if (sortBy.value === 'status') {
      cmp = (_STATUS_ORDER[a.status] ?? 9) - (_STATUS_ORDER[b.status] ?? 9)
      if (cmp === 0) cmp = a.maturity_date < b.maturity_date ? -1 : 1
    } else if (sortBy.value === 'maturity_date') {
      cmp = a.maturity_date < b.maturity_date ? -1 : 1
    } else {
      cmp = a.reference < b.reference ? -1 : 1
    }
    return sortDir.value === 'asc' ? cmp : -cmp
  })
})

// Hit-ratio and other aggregates recompute over whatever is currently
// filtered — slicing by client/sous-jacent/type shows that segment's own
// ratio, not just the whole book's.
const stats = computed(() => {
  const deals = filteredDeals.value
  const byStatus = {}
  const byOutcome = {}
  const byPayoffFamily = {}
  let nominalTotal = 0
  let payoutSum = 0
  let payoutCount = 0

  for (const d of deals) {
    byStatus[d.status] = (byStatus[d.status] || 0) + 1
    const family = dealPayoffFamily(d)
    if (family) byPayoffFamily[family] = (byPayoffFamily[family] || 0) + 1
    nominalTotal += d.nominal || 0
    if (d.resolution_outcome) {
      byOutcome[d.resolution_outcome] = (byOutcome[d.resolution_outcome] || 0) + 1
    }
    if (d.realized_payout != null) {
      payoutSum += d.realized_payout
      payoutCount++
    }
  }

  const resolved = (byOutcome.callé || 0) + (byOutcome.final || 0) + (byOutcome.ki || 0)

  return {
    total: deals.length,
    nominalTotal,
    byStatus,
    byOutcome,
    byPayoffFamily: Object.entries(byPayoffFamily).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'fr')),
    resolved,
    avgRealizedPayout: payoutCount ? payoutSum / payoutCount : null,
  }
})

const formatNominal = formatInt

async function refresh(dealId) {
  refreshingId.value = dealId
  try {
    const res = await dealsStore.refreshEvents(dealId)
    refreshResults[dealId] = res.policy === 'AUTO_YAHOO'
      ? res.message
      : describeOutcome(res.evaluation) || res.message
  } catch (e) {
    refreshResults[dealId] = `⚠ ${e.message}`
  } finally {
    refreshingId.value = null
    await dealsStore.loadDeals()
    loadWatchlist()   // a refresh can resolve a deal, dropping it off the watchlist
    if (expanded[dealId]) await loadDetail(dealId)   // open panel shows fresh events
  }
}

onMounted(async () => {
  refreshDay()
  window.addEventListener('focus', refreshDay)
  document.addEventListener('visibilitychange', refreshDay)
  await dealsStore.loadDeals()
  await loadSavedMtms(
    dealsStore.deals
      .filter(deal => ['actif', 'en_reglement'].includes(deal.status))
      .map(deal => deal.id),
  )
  loadWatchlist()
  loadAlerts()
  portfoliosStore.load()
  // Deep link from Risk Management ("/booking?deal=<id>") — open the deal's
  // detail card directly instead of landing on the watchlist.
  const dealId = Number(route.query.deal)
  if (Number.isSafeInteger(dealId) && dealId > 0) openDealDetail(dealId)
})
onUnmounted(() => {
  clearTimeout(dayTimer)
  clearTimeout(copyReferenceTimer)
  window.removeEventListener('focus', refreshDay)
  document.removeEventListener('visibilitychange', refreshDay)
})

// Shared with the panels extracted in P1-10 (U3). Declared last: every
// binding below exists by now, and provide() still runs during setup.
provide(BOOKING_CONTEXT, {
  alertError, alerts, applyShockPreset, authStore, autoExceptionEvents, canAssignPortfolio,
  canResolveAutoException, commercialScope, copiedReference, copyDealReference, dealPortfolioLabel,
  defaultExplainStart, detailErrors, details, downloadExplainNote, effectiveFundingLabel,
  effectiveProviderLabel, effectiveRateLabel, expanded, explainD1, explainD2, explainDatesValid,
  explainLoading, explainNoteLoading, explainResults, filters, formatNominal, gaugeAriaLabel,
  gaugeObservableLabel, greeksFor, greeksLoading, hasActiveFilters, lifePct, loadDetail,
  markAllRead, markRead, markingAlerts, markingAll, mtmDateFor, mtmGridChoiceFor, mtmGridFor,
  mtmLoading, mtmModeFor, mtmProgressLabel, mtmResultDate, mtmResults, obsEvents, openAutoException,
  openDealDetail, operationalEventLabel, payoffFamilyOptions, portfolioAssigning,
  portfolioAssignmentStatus, portfolios, portfoliosForDeal, productTypeOptions, refresh,
  refreshResults, refreshingId, repricingModelLabel, resetFilters, rollLoading, rollResults,
  runDealShock, runExplain, runGreeks, runMtm, runRoll, s0For, setMtmDate, setMtmGrid, setMtmMode,
  shockForm, shockHistory, shockLoading, shockPanelOpen, shockResults, sortBy, sortDir,
  sortWatchlistBy, sortedWatchlist, stats, strikeFor, tickerOptions, todayIso, toggleDealPortfolio,
  toggleDetail, toggleShockPanel, toggleSortDir, watchlist, watchlistError, watchlistLoading,
  watchlistSortTitle, wlFilter, wlRow, wlSorts, wlUnderlying,
})
</script>

<style scoped>
.watchlist-heading__content > :last-child {
  flex-shrink: 0;
}

.deal-card--alternate {
  background: var(--surface2);
}

.deal-card__actions > button {
  flex: 0 0 auto;
  min-height: 2rem;
  white-space: nowrap;
}

.deal-figures > div {
  min-width: 0;
  padding: 0.5rem 0.65rem;
}

.deal-figures > div:nth-child(odd) {
  border-right: 1px solid var(--border);
}

.deal-figures > div:nth-child(n + 3) {
  border-top: 1px solid var(--border);
}

.deal-perf.tone-pos { background: var(--positive-light); }

.deal-perf.tone-neg { background: var(--negative-light); }

.deal-barriers > * + * {
  border-top: 1px solid var(--border);
}

.barrier-gauge__caption span:first-child {
  overflow: hidden;
  color: #3d382f;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.barrier-gauge__caption span:last-child {
  flex: 0 0 auto;
  color: var(--subtle);
  font-size: 0.625rem;
}

.barrier-gauge__mark--ki { background: var(--negative); }

.barrier-gauge__mark--autocall { background: var(--positive); }

.barrier-gauge__mark span,
.barrier-gauge__cursor span {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.625rem;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
}

.barrier-gauge__mark span { bottom: calc(100% + 0.2rem); }

.barrier-gauge__mark--ki span { color: var(--negative); }

.barrier-gauge__mark--autocall span { color: var(--positive); }

.barrier-gauge__cursor span {
  top: calc(100% + 0.25rem);
  color: var(--text);
}

.deal-barrier-row__tick--ki { background: var(--negative); }

.deal-barrier-row__tick--autocall { background: var(--positive); }

.deal-panel__select.select,
.deal-panel__select.input {
  border-color: var(--panel-edge);
  background-color: var(--surface);
  color: var(--text);
  font-weight: 600;
}

.deal-panel__select.select:hover,
.deal-panel__select.select:focus,
.deal-panel__select.input:hover,
.deal-panel__select.input:focus {
  border-color: var(--panel-accent);
}

.deal-best-case span {
  color: #8a6508;
  font-weight: 600;
}

.deal-result-empty > span {
  color: #57524a;
  font-size: 0.75rem;
  line-height: 1.4;
}

/* Couleurs de signe en dernier, sous le panneau : elles doivent l'emporter
   sur toutes les couleurs de base ci-dessus. */

.deal-panel .tone-pos { color: var(--positive); }

.deal-panel .tone-neg { color: var(--negative); }
</style>
