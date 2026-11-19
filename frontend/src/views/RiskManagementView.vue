<template>
  <div class="risk-management-view flex-1 flex flex-col min-h-0 text-slate-100">

    <main class="flex-1 overflow-y-auto p-6">
      <div class="max-w-[1600px] mx-auto flex flex-col gap-3">

        <div class="page-header">
          <div class="flex items-center gap-3">
            <BackLink :fallback="{ path: '/', query: { category: 'risk_management' } }" />
            <h1 class="page-title">Risk Management</h1>
            <RouterLink to="/risk/ccr" class="btn-secondary btn-sm">Risque de contrepartie — CCR</RouterLink>
          </div>
          <div class="page-actions flex flex-wrap gap-3">
            <label class="text-xs">Périmètre des calculs
              <select :value="pf.dataScope" :disabled="calculationActive" class="select text-xs ml-2"
                @change="pf.setDataScope($event.target.value)">
                <option value="PRODUCTION">Production</option>
                <option value="UAT">Recette UAT</option>
              </select>
            </label>
            <label class="text-xs">Historiques affichés
              <select :value="pf.historyMode" :disabled="calculationActive" class="select text-xs ml-2"
                @change="pf.setHistoryMode($event.target.value)">
                <option value="CURRENT">{{ pf.scopeLabel }} · vue sélectionnée</option>
                <option value="ALL_VIEWS">{{ pf.scopeLabel }} · toutes vues et archives</option>
                <option value="LEGACY_UNQUALIFIED">Historique non qualifié</option>
              </select>
            </label>
          </div>
        </div>

        <p v-if="pf.scopeError" role="alert" class="text-xs text-amber-500">{{ pf.scopeError }}</p>
        <p class="text-xs text-slate-500">Calculs : {{ pf.scopeLabel }} · Historiques : {{ pf.historyLabel }}.</p>

        <div class="flex gap-4 flex-wrap items-start">

          <!-- ── Sélection du portefeuille actif (partagée par tous les onglets) ── -->
          <div class="card flex flex-col gap-1 w-full sm:w-64 shrink-0">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1 px-0.5">Portefeuille actif</div>
            <button class="flex items-center gap-2 text-left px-2.5 py-2 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :class="pf.view === 'global' ? 'bg-blue-600/15 text-blue-300 ring-1 ring-blue-600/40' : 'text-slate-400 hover:bg-slate-800/60'"
              :disabled="calculationActive"
              @click="pf.selectView('global')">
              <span class="text-sm">📊</span>
              <span class="flex-1">Tous portefeuilles</span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400">{{ pf.activeDealsCount }}</span>
            </button>
            <div class="border-t border-slate-800 my-1"></div>
            <button v-for="p in pf.portfolios" :key="p.id"
              class="flex items-center gap-2 text-left px-2.5 py-2 rounded-lg text-xs font-medium transition-colors min-w-0 disabled:opacity-50 disabled:cursor-not-allowed"
              :class="pf.view === p.id ? 'bg-blue-600/15 text-blue-300 ring-1 ring-blue-600/40' : 'text-slate-400 hover:bg-slate-800/60'"
              :disabled="calculationActive"
              @click="pf.selectView(p.id)">
              <span class="text-sm shrink-0">📁</span>
              <span class="flex-1 min-w-0">
                <span class="block truncate">{{ p.name }}</span>
                <span v-if="authStore.isAdmin" class="block truncate text-[9px] text-slate-600">
                  {{ p.owner_username }}{{ p.owner_entity_name ? ` · ${p.owner_entity_name}` : '' }}
                </span>
              </span>
              <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-400 shrink-0">{{ p.deal_count }}</span>
            </button>
          </div>

          <!-- ── Panneau principal ──────────────────────────────── -->
          <div class="card kpi-tile flex-1 min-w-0 flex flex-col gap-3">
            <div class="flex items-center gap-3 flex-wrap">
              <div class="text-sm font-bold text-slate-100">
                {{ pf.view === 'global' ? '📊 Tous portefeuilles' : `📁 ${pf.label}` }}
              </div>
              <label class="ml-auto flex items-center gap-2 text-[10px] text-slate-400">
                Date des Greeks
                <input v-model="pf.valuationDate" type="date" :max="todayIso"
                  :disabled="calculationActive" class="input text-xs py-1 w-36" />
              </label>
              <button class="btn-secondary text-xs px-3 py-1.5" :disabled="calculationActive || !pf.riskMembers.length"
                @click="recomputePortfolio">
                <span v-if="recomputing"
                  class="w-3 h-3 border-2 border-slate-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                🔄 Recalculer{{ recomputing ? ` (${recomputeDone}/${recomputeTotal})` : '' }}
              </button>
            </div>

            <div v-if="calculationProgress"
              class="rounded-lg border border-blue-900/60 bg-blue-950/20 px-3 py-2">
              <div class="flex items-center gap-2 text-[10px] text-slate-400 mb-1.5">
                <span class="font-semibold text-blue-300">{{ calculationProgress.label }}</span>
                <span v-if="calculationProgress.total" class="font-mono">
                  {{ calculationProgress.completed }}/{{ calculationProgress.total }}
                </span>
                <span v-else>calcul en cours</span>
                <span class="ml-auto font-mono">{{ formatElapsed(calculationElapsed) }}</span>
              </div>
              <div class="h-1.5 rounded-full bg-slate-800 overflow-hidden">
                <div class="h-full rounded-full bg-blue-500 transition-all duration-300"
                  :class="calculationProgress.total ? '' : 'animate-pulse'"
                  :style="{ width: calculationProgress.total ? `${calculationProgress.percent}%` : '45%' }"></div>
              </div>
            </div>

            <AlertMessage v-if="recomputeNotice" :kind="recomputeFailures.length ? 'warning' : 'success'"
              dismissible @dismiss="recomputeNotice = ''">
              {{ recomputeNotice }}
            </AlertMessage>

            <!-- Menu du module : gestion / analyses (d'autres viendront) -->
            <div class="flex border-b border-slate-800 -mb-1">
              <button @click="activeTab = 'portfolios'"
                :class="activeTab === 'portfolios' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                Portefeuilles ({{ pf.allMembers.length }})
              </button>
              <button @click="activeTab = 'greeks'"
                :class="activeTab === 'greeks' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                Greeks
              </button>
              <button @click="activeTab = 'contreparties'"
                :class="activeTab === 'contreparties' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                🏦 Contreparties
              </button>
              <button @click="activeTab = 'chocs'"
                :class="activeTab === 'chocs' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                ⚡ Chocs
              </button>
              <button @click="activeTab = 'smile'"
                :class="activeTab === 'smile' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                〰 Smile
              </button>
              <button @click="activeTab = 'var'"
                :class="activeTab === 'var' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                📉 VaR
              </button>
              <button @click="activeTab = 'pnl'"
                :class="activeTab === 'pnl' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                P&L
              </button>
              <button @click="activeTab = 'barrieres'"
                :class="activeTab === 'barrieres' ? 'border-b-2 border-blue-500 text-slate-100' : 'text-slate-500 hover:text-slate-300'"
                class="px-4 py-2 text-xs font-medium transition-colors">
                📍 Barrières
              </button>
            </div>

            <!-- ══ Onglet Greeks agrégés ═════════════════════════ -->
            <template v-if="activeTab === 'greeks'">
                <RiskGreeksTab />
              </template>

            <!-- ══ Onglet Contreparties : concentration & limites ═ -->
            <template v-else-if="activeTab === 'contreparties'">
                <RiskCounterpartiesTab />
              </template>

            <!-- ══ Onglet Chocs ══════════════════════════════════ -->
            <template v-else-if="activeTab === 'chocs'">
                <RiskShocksTab />
            </template>

            <!-- ══ Onglet VaR/ES ═════════════════════════════════ -->
            <template v-else-if="activeTab === 'var'">
                <RiskVarTab />
            </template>

            <!-- ══ Onglet P&L ════════════════════════════════════ -->
            <template v-else-if="activeTab === 'pnl'">
              <RiskPnlTab />
            </template>

            <!-- ══ Onglet risque de smile ══════════════════════════ -->
            <template v-else-if="activeTab === 'smile'">
              <RiskSmileTab />
            </template>

            <!-- ══ Onglet Barrières : proximité aux barrières ═══════ -->
            <template v-else-if="activeTab === 'barrieres'">
              <RiskBarriersTab />
            </template>

            <!-- ══ Onglet Portefeuilles : création, gestion, composition ══ -->
            <template v-else>
<RiskPortfoliosTab />
            </template>

          </div>
        </div>

      </div>
    </main>
  </div>
</template>

<script setup>
import RiskGreeksTab from './risk/RiskGreeksTab.vue'
import RiskCounterpartiesTab from './risk/RiskCounterpartiesTab.vue'
import RiskShocksTab from './risk/RiskShocksTab.vue'
import RiskVarTab from './risk/RiskVarTab.vue'
import RiskPnlTab from './risk/RiskPnlTab.vue'
import RiskSmileTab from './risk/RiskSmileTab.vue'
import RiskBarriersTab from './risk/RiskBarriersTab.vue'
import RiskPortfoliosTab from './risk/RiskPortfoliosTab.vue'
import { RISK_CONTEXT } from './risk/context.js'
import BackLink from '../components/ui/BackLink.vue'
import { ref, reactive, computed, onMounted, onUnmounted, watch, provide } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useDealsStore } from '../stores/deals.js'
import { usePortfoliosStore, shockPresets, blankShockForm, blankVarForm } from '../stores/portfolios.js'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'
import { formatInt } from '../utils/format.js'
import { dealRiskState, localTodayIso } from '../utils/riskDates.js'
import { runConcurrentPool } from '../utils/concurrentPool.js'
import AlertMessage from '../components/ui/AlertMessage.vue'
import { confirmer } from '../composables/useConfirm.js'
import { formatElapsed } from './risk/riskLabels.js'

const route = useRoute()
const router = useRouter()
const dealsStore = useDealsStore()
const pf = usePortfoliosStore()
const authStore = useAuthStore()

// Le sous-menu Risk Management de l'accueil route vers /risk?tab=... — chaque
// entrée (Création de portefeuille / Chocs / Explication de P&L) atterrit
// directement sur sa section.
const VALID_TABS = ['portfolios', 'greeks', 'contreparties', 'chocs', 'smile', 'var', 'pnl', 'barrieres']
const activeTab = ref(VALID_TABS.includes(route.query.tab) ? route.query.tab : 'portfolios')
watch(() => route.query.tab, (t) => {
  if (VALID_TABS.includes(t)) activeTab.value = t
})

// Barrières is lazy (see stores/portfolios.js loadBarriers doc) — fetch once
// when the tab is first opened, not on every portfolio switch.
watch(activeTab, (t) => {
  if (t === 'barrieres' && !pf.barriers && !pf.barriersLoading) pf.loadBarriers()
})
const expandedUnderlying = ref(null)
const expandedCorrPair = ref(null)
const expandedCounterparty = ref(null)
const newPortfolioName = ref('')
const newPortfolioUserId = ref(authStore.user?.id || null)
const creatingPortfolio = ref(false)
const portfolioAssigning = reactive({})
const portfolioError = ref('')
const portfolioNotice = ref('')
const todayIso = localTodayIso()

const formatNominal = formatInt

function riskState(deal) {
  return dealRiskState(deal, pf.valuationDate)
}

function greekValuationDate(deal) {
  const data = deal.greeks?.market_used?.data || {}
  return deal.greeks?.valuation_date
    || data.contractual_history?.requested_end
    || data.requested_asof
    || null
}

function greeksMatchSelectedDate(deal) {
  if (pf.risk?.valuation_date === pf.valuationDate) {
    return pf.risk.deals_included?.some(row => row.id === deal.id) || false
  }
  return !!deal.greeks_computed_at && greekValuationDate(deal) === pf.valuationDate
}

function greekExecutionTitle(deal) {
  const included = pf.risk?.deals_included?.find(row => row.id === deal.id)
  const computedAt = included?.greeks_computed_at || deal.greeks_computed_at
  return computedAt
    ? `Calcul exécuté le ${new Date(computedAt).toLocaleString('fr-FR')}`
    : 'Calcul daté disponible'
}

const portfolioOwners = computed(() => {
  const owners = new Map()
  if (authStore.user?.id) owners.set(authStore.user.id, {
    id: authStore.user.id,
    username: authStore.user.username,
    entity: null,
  })
  for (const p of pf.portfolios) {
    owners.set(p.user_id, {
      id: p.user_id,
      username: p.owner_username || `Compte #${p.user_id}`,
      entity: p.owner_entity_name || null,
    })
  }
  return [...owners.values()].sort((a, b) => a.username.localeCompare(b.username, 'fr'))
})

watch(portfolioOwners, owners => {
  if (!owners.length) return
  if (!owners.some(owner => owner.id === newPortfolioUserId.value)) {
    newPortfolioUserId.value = authStore.user?.id || owners[0].id
  }
}, { immediate: true })

function portfoliosForDeal(deal) {
  return pf.portfolios.filter(p => p.user_id === deal.user_id)
}

const hasMixedVegaScopes = computed(() =>
  Object.values(pf.risk?.per_underlying || {}).some(bucket => bucket.vega_scope_mixed)
)

const riskMetricRows = computed(() => {
  const labels = { delta: 'Delta', gamma: 'Gamma', vega: 'Vega', theta: 'Theta', rho: 'Rho', corr: 'Corrélation' }
  return Object.entries(pf.risk?.metric_coverage || {}).filter(([, row]) => row.required > 0).map(([key, row]) => ({
    key, label: labels[key] || key, available: row.available, required: row.required,
    complete: row.status === 'COMPLETE',
    detail: [
      ...(row.missing || []).map(x => `${x.reference} : ${x.reason}`),
      ...(row.sources || []).map(x => `${x.reference} · ${x.run_id ? `calcul #${x.run_id}` : 'cache ancien sans référence de calcul'} · ${x.valuation_date} · ${x.computed_at || 'date de calcul inconnue'}`),
    ].join('\n'),
  }))
})

// Deal drill-down lives in Booking — route there with the deal pre-expanded.
function openDealDetail(id) {
  router.push({ path: '/booking', query: { deal: id } })
}

// ── Gestion des portefeuilles ────────────────────────────────────────
async function createPortfolio() {
  const name = newPortfolioName.value.trim()
  if (!name || creatingPortfolio.value) return
  creatingPortfolio.value = true
  portfolioError.value = ''
  portfolioNotice.value = ''
  try {
    const created = await pf.create(name, authStore.isAdmin ? newPortfolioUserId.value : null)
    newPortfolioName.value = ''
    portfolioNotice.value = `Portefeuille « ${created.name} » créé. Vous pouvez maintenant y affecter des deals.`
  } catch (e) {
    portfolioError.value = e.message
  } finally {
    creatingPortfolio.value = false
  }
}

async function renamePortfolio(p) {
  const name = prompt('Nouveau nom du portefeuille :', p.name)
  if (!name || !name.trim() || name.trim() === p.name) return
  portfolioError.value = ''
  portfolioNotice.value = ''
  try {
    await pf.rename(p, name.trim())
    portfolioNotice.value = `Portefeuille renommé « ${name.trim()} ».`
  } catch (e) {
    portfolioError.value = e.message
  }
}

async function deletePortfolio(p) {
  if (!await confirmer({ titre: `Supprimer « ${p.name} » ?`,
                       message: "Seules les appartenances à ce portefeuille seront supprimées. "
                              + 'Les deals et tous leurs calculs seront conservés.',
                       confirmer: 'Supprimer', danger: true })) return
  portfolioError.value = ''
  portfolioNotice.value = ''
  try {
    await pf.remove(p)
    portfolioNotice.value = `Portefeuille « ${p.name} » supprimé. Les deals et leurs calculs sont conservés.`
  } catch (e) {
    portfolioError.value = e.message
  }
}

async function togglePortfolioMembership(deal, portfolioId, checked) {
  if (portfolioAssigning[deal.id]) return
  const target = pf.portfolios.find(p => p.id === portfolioId)
  const currentIds = deal.portfolio_ids || []
  const nextIds = checked
    ? [...new Set([...currentIds, portfolioId])]
    : currentIds.filter(id => id !== portfolioId)
  portfolioAssigning[deal.id] = true
  portfolioError.value = ''
  portfolioNotice.value = ''
  try {
    await pf.setDealPortfolios(deal.id, nextIds)
    portfolioNotice.value = checked
      ? `${deal.reference} ajouté à « ${target?.name || 'portefeuille sélectionné'} ».`
      : `${deal.reference} retiré de « ${target?.name || 'portefeuille sélectionné'} ».`
  } catch (e) {
    portfolioError.value = `${deal.reference} : ${e.message}`
  } finally {
    portfolioAssigning[deal.id] = false
  }
}

// ── Risque de smile, paramètres explicites par modèle ───────────────
const smileForm = reactive({
  atm_vol_pts: 0, skew_pts: 0, curvature_pts: 0,
  sabr_alpha_pts: 0, sabr_rho_pts: 0, sabr_nu_pts: 0,
  heston_v0_pts: 0, heston_theta_pts: 0, heston_rho_pts: 0, heston_xi_pts: 0,
  label: '', recalibrate: 'none',
})
const smileError = ref('')
const smileTarget = ref('all')
const smileUnderlyings = computed(() => {
  const seen = new Map()
  for (const deal of pf.members) {
    for (const underlying of deal.underlyings || []) {
      const key = underlying.ticker || underlying.name
      if (key && !seen.has(key)) {
        seen.set(key, { key, label: underlying.ticker
          ? `${underlying.name || underlying.ticker} · ${underlying.ticker}`
          : underlying.name })
      }
    }
  }
  return [...seen.values()].sort((a, b) => a.label.localeCompare(b.label, 'fr'))
})
const smileHasShock = computed(() => Object.entries(smileForm).some(([key, value]) =>
  key.endsWith('_pts') && Number(value) !== 0))

async function runSmile() {
  smileError.value = ''
  try {
    const fields = Object.fromEntries(Object.entries(smileForm)
      .filter(([key]) => key.endsWith('_pts')))
    const payload = smileTarget.value === 'all'
      ? { ...smileForm }
      : {
          ...Object.fromEntries(Object.keys(fields).map(key => [key, 0])),
          label: smileForm.label,
          recalibrate: smileForm.recalibrate,
          underlying_overrides: { [smileTarget.value]: fields },
        }
    await pf.runSmileRisk(payload)
  } catch (e) {
    smileError.value = e.message
  }
}

// ── Recalcul des Greeks par deal (batch) ─────────────────────────────
const recomputing = ref(false)
const recomputeDone = ref(0)
const recomputeTotal = ref(0)
const recomputeFailures = ref([])
const recomputeNotice = ref('')
const PORTFOLIO_GREEK_CONCURRENCY = 2

async function recomputePortfolio() {
  const memberIds = pf.riskMembers.map(d => d.id)
  if (!memberIds.length) return
  recomputing.value = true
  recomputeDone.value = 0
  recomputeTotal.value = memberIds.length
  recomputeFailures.value = []
  recomputeNotice.value = ''
  try {
    const results = await runConcurrentPool(memberIds, async id => {
      const response = await apiFetch(`/api/deals/${id}/greeks`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            recalibrate: 'none',
            valuation_date: pf.valuationDate,
          }),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        const detail = payload.detail
        throw new Error(typeof detail === 'string' ? detail : detail?.message || 'Calcul refusé')
      }
      return id
    }, {
      concurrency: PORTFOLIO_GREEK_CONCURRENCY,
      onSettled: () => { recomputeDone.value += 1 },
    })
    recomputeFailures.value = results.flatMap((result, index) => result.status === 'rejected'
      ? [{ id: memberIds[index], reason: result.reason?.message || 'Erreur de calcul' }]
      : [])
    const succeeded = memberIds.length - recomputeFailures.value.length
    recomputeNotice.value = recomputeFailures.value.length
      ? `${succeeded}/${memberIds.length} calcul(s) terminés. ${recomputeFailures.value.length} deal(s) en erreur.`
      : `${succeeded} calcul(s) de Greeks terminés à la date sélectionnée.`
  } finally {
    try {
      await dealsStore.loadDeals()
      await pf.loadRisk()
    } finally {
      recomputing.value = false
    }
  }
}

// ── Chocs (portefeuille / global) ────────────────────────────────────
const shockForm = reactive(blankShockForm())
const shockLoading = ref(false)
const shockResult = ref(null)

function applyShockPreset(label) {
  const preset = shockPresets.find(p => p.label === label)
  if (!preset) return
  Object.assign(shockForm, {
    spot_shock_pct: preset.spot_shock_pct, vol_shock_pts: preset.vol_shock_pts,
    rate_shock_bp: preset.rate_shock_bp, corr_shock_pts: preset.corr_shock_pts,
  })
}

async function runPortfolioShock() {
  shockLoading.value = true
  shockResult.value = null
  try {
    const global = pf.view === 'global'
    shockResult.value = await pf.runShock(global ? 'global' : 'portfolio',
                                          global ? null : pf.view, shockForm)
  } catch (e) {
    shockResult.value = { error: e.message }
  } finally {
    shockLoading.value = false
  }
}

// ── VaR/ES study (portefeuille / global) ─────────────────────────────
const varForm = reactive(blankVarForm())
const varAdvancedOpen = ref(false)
// deals_skipped only comes back on the launch (POST) response, never on a
// later poll of GET /var/{id} — kept in its own ref (rather than stashed
// onto pf.varStudy) since the poll loop overwrites pf.varStudy.value
// asynchronously and could otherwise race with this assignment.
const varDealsSkipped = ref([])
const varLaunchError = ref('')

const varExcludedDeals = computed(() => {
  const resultDeals = pf.varStudy?.result?.excluded_deals
  if (resultDeals?.length) return resultDeals
  const persisted = pf.varStudy?.params?.preflight_exclusions
  if (persisted?.length) return persisted
  return varDealsSkipped.value
})

const varPublishedScope = computed(() => {
  const result = pf.varStudy?.result
  if (!result) return null
  if (result.global_status === 'complete') return result
  if (result.global_status === 'incomplete') return result.reduced_scope || null
  // Historical batches created before the publication gate.
  return result.historical || result.parametric ? result : null
})

const varPublishedScopeLabel = computed(() =>
  varPublishedScope.value?.label || 'VaR du portefeuille demandé')

async function launchVarStudy() {
  varDealsSkipped.value = []
  varLaunchError.value = ''
  try {
    const launched = await pf.launchVar(varForm)
    varDealsSkipped.value = launched.deals_skipped || []
  } catch (e) {
    const detail = e.computeDetail
    if (detail?.code === 'COMPUTE_CONFIRMATION_REQUIRED') {
      const x = detail.estimate || {}
      const accepted = await confirmer({
        titre: 'Confirmer cette VaR lourde ?',
        message: `${Number(x.cells || 0).toLocaleString('fr-FR')} valorisations, ` +
          `${Number(x.paths_per_scenario || 0).toLocaleString('fr-FR')} trajectoires chacune, ` +
          `mémoire de pointe estimée ${x.estimated_peak_mb || 0} Mo.`,
        confirmer: 'Lancer la VaR',
      })
      if (accepted) {
        try {
          const launched = await pf.launchVar({
            ...varForm, confirmation_token: detail.confirmation_token,
          })
          varDealsSkipped.value = launched.deals_skipped || []
          return
        } catch (retryError) {
          varLaunchError.value = retryError.message
          return
        }
      }
      return
    }
    varLaunchError.value = e.message
  }
}

// ── P&L explain (portefeuille / global) ──────────────────────────────
const pnlD1 = ref('')                  // vide = origine de chaque deal
const pnlD2 = ref(todayIso)
const pnlLoading = ref(false)
const pnlResult = ref(null)

const pnlHasCorr = computed(() =>
  !!pnlResult.value?.steps?.some(st => st.key === 'corr'))

async function runPnl() {
  pnlLoading.value = true
  pnlResult.value = null
  try {
    pnlResult.value = await pf.runPnlExplain({
      date1: pnlD1.value || null,
      date2: pnlD2.value || todayIso,
      recalibrate: 'realized',
    })
  } catch (e) {
    pnlResult.value = { error: e.message }
  } finally {
    pnlLoading.value = false
  }
}

// ── Progression unifiée des calculs de portefeuille ────────────────
// Greeks et VaR exposent un compteur exact. Les endpoints synchrones
// (choc, smile, P&L, barrières) n'exposent pas encore leurs étapes internes :
// la barre reste alors indéterminée mais le temps écoulé reste visible.
const calculationProgress = computed(() => {
  if (recomputing.value) {
    const total = recomputeTotal.value
    const completed = recomputeDone.value
    return {
      key: 'greeks', label: 'Calcul des Greeks du portefeuille', completed, total,
      percent: total ? Math.round(completed / total * 100) : 0,
    }
  }
  if (shockLoading.value) return { key: 'shock', label: 'Repricing du choc portefeuille' }
  if (pf.smileLoading) return { key: 'smile', label: 'Repricing du smile portefeuille' }
  if (pf.varLaunching || pf.varPolling) {
    const total = Number(pf.varStudy?.total_jobs || 0)
    const completed = Number(pf.varStudy?.completed_jobs || 0) + Number(pf.varStudy?.failed_jobs || 0)
    return {
      key: 'var', label: pf.varLaunching ? 'Préparation de la VaR' : 'Calcul de la VaR',
      completed, total, percent: total ? Math.round(completed / total * 100) : 0,
    }
  }
  if (pnlLoading.value) return { key: 'pnl', label: 'Explication du P&L portefeuille' }
  if (pf.barriersLoading) return { key: 'barriers', label: 'Analyse des barrières du portefeuille' }
  return null
})
const calculationActive = computed(() => calculationProgress.value !== null)
const calculationElapsed = ref(0)
let calculationTimer = null

watch(() => calculationProgress.value?.key || null, key => {
  if (calculationTimer) clearInterval(calculationTimer)
  calculationTimer = null
  calculationElapsed.value = 0
  if (key) {
    const startedAt = Date.now()
    calculationTimer = setInterval(() => {
      calculationElapsed.value = Math.floor((Date.now() - startedAt) / 1000)
    }, 1000)
  }
}, { immediate: true })

watch(() => [pf.dataScope, pf.view], () => {
  shockResult.value = null
  pnlResult.value = null
  if (activeTab.value === 'barrieres') pf.loadBarriers().catch(e => { pf.scopeError = e.message })
})

onMounted(() => {
  const rememberedVarBatchId = pf.varStudy?.batch_id
  dealsStore.loadDeals()
  pf.load()
  pf.loadRisk()
  pf.loadExposure()
  pf.loadVarHistory()
  // The view deliberately stops its timer while unmounted. Refresh the
  // remembered batch on return so a study completed in the meantime cannot
  // remain displayed with an old "En cours" counter.
  if (rememberedVarBatchId) pf.openVarBatch(rememberedVarBatchId)
  pf.loadShockHistory(pf.view === 'global' ? 'global' : 'portfolio',
                      pf.view === 'global' ? null : pf.view)
  pf.loadShockHistory(pf.view === 'global' ? 'smile_global' : 'smile_portfolio',
                      pf.view === 'global' ? null : pf.view)
})

watch(() => pf.valuationDate, (value) => {
  if (!value || value > todayIso) return
  pf.loadRisk()
})

// A VaR study's poll loop uses setTimeout, not a Vue-managed watcher — must
// be stopped explicitly on unmount or it keeps polling (and holds a
// reference to this closed-over component) after the user navigates away.
onUnmounted(() => {
  pf.stopVarPolling()
  if (calculationTimer) clearInterval(calculationTimer)
})

// Shared with the panels extracted in P1-10 (U3). Declared last: every
// binding below exists by now, and provide() still runs during setup.
provide(RISK_CONTEXT, {
  applyShockPreset, authStore, calculationActive, createPortfolio, creatingPortfolio,
  deletePortfolio, expandedCorrPair, expandedCounterparty, expandedUnderlying, formatNominal,
  greekExecutionTitle, greeksMatchSelectedDate, hasMixedVegaScopes, launchVarStudy,
  newPortfolioName, newPortfolioUserId, openDealDetail, pf, pnlD1, pnlD2, pnlHasCorr, pnlLoading,
  pnlResult, portfolioAssigning, portfolioError, portfolioNotice, portfolioOwners,
  portfoliosForDeal, renamePortfolio, riskMetricRows, riskState, runPnl, runPortfolioShock,
  runSmile, shockForm, shockLoading, shockResult, smileError, smileForm, smileHasShock, smileTarget,
  smileUnderlyings, togglePortfolioMembership, varAdvancedOpen, varExcludedDeals, varForm,
  varLaunchError, varPublishedScope, varPublishedScopeLabel,
})
</script>

<style scoped>
.risk-management-view table td > .flex {
  justify-content: center;
}
</style>
