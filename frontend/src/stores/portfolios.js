import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { apiFetch } from '../utils/api.js'
import { useDealsStore } from './deals.js'
import { dealRiskState, localTodayIso } from '../utils/riskDates.js'

async function apiError(res, fallback) {
  const data = await res.json().catch(() => ({}))
  const detail = data?.detail
  if (typeof detail === 'string') return new Error(detail)
  if (detail?.message) return new Error(detail.message)
  return new Error(fallback)
}

// Shock presets are plain prefill data (spot%/vol pts/rate bp/corr pts) — no
// backend catalog, easy to tweak here without touching the API. Shared by the
// deal-level shock panel (Booking) and the portfolio Chocs tab (Risk Management).
export const shockPresets = [
  { label: 'Crash actions -20%', spot_shock_pct: -20, vol_shock_pts: 10, rate_shock_bp: 0, corr_shock_pts: 0 },
  { label: 'Rally actions +20%', spot_shock_pct: 20, vol_shock_pts: -5, rate_shock_bp: 0, corr_shock_pts: 0 },
  { label: 'Choc vol +10pts', spot_shock_pct: 0, vol_shock_pts: 10, rate_shock_bp: 0, corr_shock_pts: 0 },
  { label: 'Choc taux +100bp', spot_shock_pct: 0, vol_shock_pts: 0, rate_shock_bp: 100, corr_shock_pts: 0 },
  { label: 'Choc taux -100bp', spot_shock_pct: 0, vol_shock_pts: 0, rate_shock_bp: -100, corr_shock_pts: 0 },
  // Isole le risque de corrélation seul — les worst-of (Athena/Phoenix) perdent
  // de la valeur de "dispersion" quand les sous-jacents se corrèlent plus,
  // exactement la dynamique d'une crise (cf. Crise systémique ci-dessous, qui
  // la bundle avec spot/vol/taux) mais ici isolée pour voir l'effet seul.
  { label: 'Choc corrélation +20pts', spot_shock_pct: 0, vol_shock_pts: 0, rate_shock_bp: 0, corr_shock_pts: 20 },
  { label: 'Crise systémique', spot_shock_pct: -30, vol_shock_pts: 20, rate_shock_bp: -100, corr_shock_pts: 20 },
]

export function blankShockForm() {
  return { spot_shock_pct: 0, vol_shock_pts: 0, rate_shock_bp: 0, corr_shock_pts: 0 }
}

// VaR study defaults — mirrors backend/app/api/var.py's VarRequest defaults
// exactly, so a freshly-opened form already reflects what the API would do
// on its own if these fields were omitted.
export function blankVarForm() {
  return {
    method: 'both', confidence: 0.95, horizon_days: 1, lookback_years: 5.0,
    n_parametric: 2000, n_paths_per_scenario: 3000, max_workers: 4,
  }
}

// Shared data backbone of the portfolio world: the portfolio list itself, the
// active selection ('global' | portfolio id), aggregated risk, shock runs and
// their history, and the portfolio-level P&L explain. Booking (deal-level
// shock panel, portfolio dropdowns) and Risk Management both plug in here so
// neither view duplicates the other's state.
export const usePortfoliosStore = defineStore('portfolios', () => {
  const dealsStore = useDealsStore()

  const portfolios = ref([])
  const dataScope = ref('PRODUCTION')
  const historyMode = ref('CURRENT')
  const scopeError = ref('')
  let contextVersion = 0
  const historyScope = computed(() => historyMode.value === 'LEGACY_UNQUALIFIED' ? historyMode.value : dataScope.value)
  const scopeLabel = computed(() => dataScope.value === 'UAT' ? 'Recette UAT' : 'Production')
  const historyLabel = computed(() => historyScope.value === 'LEGACY_UNQUALIFIED' ? 'Historique non qualifié' : scopeLabel.value + (historyMode.value === 'ALL_VIEWS' ? ' · toutes vues' : ''))
  const matchesScope = d => (d.uat_batch_id != null) === (dataScope.value === 'UAT')
  const withScope = url => `${url}${url.includes('?') ? '&' : '?'}data_scope=${dataScope.value}`
  const historyToken = () => `${contextVersion}:${historyMode.value}:${historyScope.value}`

  const view = ref('global')            // 'global' | portfolio id
  const valuationDate = ref(localTodayIso())
  const risk = ref(null)
  const riskLoading = ref(false)
  const exposure = ref(null)
  const exposureLoading = ref(false)
  const shockHistory = reactive({})     // deal id | 'portfolio:<id>' | 'global:' → runs

  const label = computed(() => {
    const p = portfolios.value.find(p => p.id === view.value)
    return p ? p.name : ''
  })

  const isDefaultView = computed(() => {
    const p = portfolios.value.find(p => p.id === view.value)
    return !!(p && p.is_default)
  })

  const allMembers = computed(() => {
    const scoped = dealsStore.deals.filter(matchesScope)
    if (view.value === 'global') return scoped
    return scoped.filter(d => (d.portfolio_ids || []).includes(view.value))
  })

  const riskMembers = computed(() => allMembers.value.filter(
    deal => dealRiskState(deal, valuationDate.value).active))

  const activeDealsCount = computed(() => dealsStore.deals.filter(
    deal => matchesScope(deal) && dealRiskState(deal, valuationDate.value).active).length)

  const members = computed(() => allMembers.value.filter(d => d.status === 'actif'))

  async function scopedRead(url, ticket = contextVersion) {
    const res = await apiFetch(url)
    if (!res.ok) throw await apiError(res, 'Chargement du périmètre impossible')
    const data = await res.json()
    return ticket === contextVersion ? data : null
  }


  async function load() {
    const data = await scopedRead(withScope('/api/portfolios'))
    if (data !== null) portfolios.value = data
  }

  async function create(name, userId = null) {
    const body = { name }
    if (userId != null) body.user_id = Number(userId)
    const res = await apiFetch('/api/portfolios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw await apiError(res, 'Création du portefeuille impossible')
    const created = await res.json()
    await load()
    return created
  }

  async function rename(p, name) {
    const res = await apiFetch(`/api/portfolios/${p.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) throw await apiError(res, 'Renommage du portefeuille impossible')
    await load()
  }

  async function remove(p) {
    const res = await apiFetch(`/api/portfolios/${p.id}`, { method: 'DELETE' })
    if (!res.ok) throw await apiError(res, 'Suppression du portefeuille impossible')
    if (view.value === p.id) { view.value = 'global'; clearSelectionResults() }
    await dealsStore.loadDeals()
    await load()
    await loadRisk()
  }

  async function setDealPortfolios(dealId, rawIds) {
    const portfolioIds = [...new Set(rawIds.map(Number))]
    if (portfolioIds.some(id => !Number.isInteger(id) || id <= 0)) {
      throw new Error('La sélection contient un portefeuille invalide')
    }
    const res = await apiFetch(`/api/deals/${dealId}/portfolios`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ portfolio_ids: portfolioIds }),
    })
    if (!res.ok) throw await apiError(res, "L'assignation du deal a échoué")
    const assigned = await res.json()
    await dealsStore.loadDeals()
    await load()
    if (risk.value) await loadRisk()
    if (exposure.value) await loadExposure()
    barriers.value = null
    return assigned
  }

  // Compatibility for callers outside the two portfolio selectors: adding a
  // portfolio no longer removes the memberships already present.
  async function assignDeal(dealId, rawValue) {
    const deal = dealsStore.deals.find(d => d.id === dealId)
    const portfolioId = Number(rawValue)
    return setDealPortfolios(dealId, [...(deal?.portfolio_ids || []), portfolioId])
  }

  async function loadRisk() {
    const ticket = contextVersion
    riskLoading.value = true
    try {
      const url = view.value === 'global'
        ? `/api/portfolios/risk-global?valuation_date=${encodeURIComponent(valuationDate.value)}`
        : `/api/portfolios/${view.value}/risk?valuation_date=${encodeURIComponent(valuationDate.value)}`
      const data = await scopedRead(withScope(url), ticket)
      if (data !== null) risk.value = data
    } finally {
      if (ticket === contextVersion) riskLoading.value = false
    }
  }

  async function loadExposure() {
    const ticket = contextVersion
    exposureLoading.value = true
    try {
      const url = view.value === 'global'
        ? '/api/portfolios/exposure-by-counterparty'
        : `/api/portfolios/${view.value}/exposure-by-counterparty`
      const data = await scopedRead(withScope(url), ticket)
      if (data !== null) exposure.value = data
    } finally {
      if (ticket === contextVersion) exposureLoading.value = false
    }
  }

  // Barrier proximity uses the existing dated market-data/cache service per
  // deal. It can be more expensive than reading persisted Greeks, so it is
  // not auto-loaded on
  // every portfolio switch — only when the Barrières tab is actually opened
  // (see RiskManagementView.vue), same "expensive, explicit" treatment as
  // the VaR study and P&L explain below.
  const barriers = ref(null)
  const barriersLoading = ref(false)

  async function loadBarriers() {
    const ticket = contextVersion
    barriersLoading.value = true
    try {
      const url = view.value === 'global'
        ? '/api/portfolios/barriers-global'
        : `/api/portfolios/${view.value}/barriers`
      const data = await scopedRead(withScope(url), ticket)
      if (data !== null) barriers.value = data
    } finally {
      if (ticket === contextVersion) barriersLoading.value = false
    }
  }

  function clearSelectionResults() {
    contextVersion += 1
    stopVarPolling()
    risk.value = exposure.value = barriers.value = smileResult.value = varStudy.value = null
    riskLoading.value = exposureLoading.value = barriersLoading.value = smileLoading.value = false
    varLaunching.value = false
    varHistory.value = []
    scopeError.value = ''
  }

  async function reloadSelection() {
    const ticket = contextVersion
    try {
      await Promise.all([load(), loadRisk(), loadExposure(), loadVarHistory(),
        loadShockHistory(view.value === 'global' ? 'global' : 'portfolio', view.value === 'global' ? null : view.value),
        loadShockHistory(view.value === 'global' ? 'smile_global' : 'smile_portfolio', view.value === 'global' ? null : view.value)])
    } catch (e) { if (ticket === contextVersion) scopeError.value = e.message }
  }

  function selectView(v) {
    view.value = v
    clearSelectionResults()
    return reloadSelection()
  }

  function setDataScope(value) {
    if (!['PRODUCTION', 'UAT'].includes(value)) throw new Error('Périmètre invalide')
    if (dataScope.value === value) return Promise.resolve()
    dataScope.value = value
    historyMode.value = 'CURRENT'
    clearSelectionResults()
    return reloadSelection()
  }

  async function setHistoryMode(value) {
    if (!['CURRENT', 'ALL_VIEWS', 'LEGACY_UNQUALIFIED'].includes(value)) throw new Error('Historique invalide')
    historyMode.value = value
    stopVarPolling()
    varStudy.value = null
    varHistory.value = []
    try {
      await Promise.all([loadVarHistory(),
        loadShockHistory(view.value === 'global' ? 'global' : 'portfolio', view.value === 'global' ? null : view.value),
        loadShockHistory(view.value === 'global' ? 'smile_global' : 'smile_portfolio', view.value === 'global' ? null : view.value)])
    } catch (e) { scopeError.value = e.message }
  }

  // Individual contracts retain their own history key. Aggregate keys also
  // include the archived origin so a scope switch never reuses another book.
  function historyKey(scope, id) {
    return scope === 'deal' ? id : `${historyMode.value}:${historyScope.value}:${scope}:${id ?? ''}`
  }

  async function loadShockHistory(scope, id) {
    const ticket = historyToken()
    const key = historyKey(scope, id)
    const params = new URLSearchParams({ scope, data_scope: historyScope.value, limit: '5' })
    if (scope !== 'deal' && historyMode.value !== 'CURRENT') params.set('all_views', 'true')
    if (scope === 'deal') {
      params.set('deal_id', id)
      const deal = dealsStore.deals.find(d => d.id === id)
      params.set('data_scope', deal?.uat_batch_id != null ? 'UAT' : 'PRODUCTION')
    } else if (id != null) params.set('portfolio_id', id)
    const res = await apiFetch(`/api/shocks?${params}`)
    if (!res.ok) throw await apiError(res, 'Historique des chocs indisponible')
    let data = await res.json()
    // An explicitly selected Deal can retain unqualified legacy studies;
    // they are labelled individually and never enter an aggregate total.
    if (scope === 'deal') {
      params.set('data_scope', 'LEGACY_UNQUALIFIED')
      const legacy = await apiFetch(`/api/shocks?${params}`)
      if (!legacy.ok) throw await apiError(legacy, 'Ancien historique des chocs indisponible')
      data = [...data, ...await legacy.json()].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5)
    }
    if (ticket === historyToken()) shockHistory[key] = data
  }

  const currentShockHistory = computed(() => {
    const key = historyKey(view.value === 'global' ? 'global' : 'portfolio', view.value === 'global' ? null : view.value)
    return shockHistory[key] || []
  })

  const currentSmileHistory = computed(() => {
    const key = historyKey(view.value === 'global' ? 'smile_global' : 'smile_portfolio', view.value === 'global' ? null : view.value)
    return shockHistory[key] || []
  })

  async function runShock(scope, id, form) {
    const ticket = contextVersion
    const deal = scope === 'deal' ? dealsStore.deals.find(d => d.id === id) : null
    const origin = scope === 'deal' ? (deal?.uat_batch_id != null ? 'UAT' : 'PRODUCTION') : dataScope.value
    const url = scope === 'deal' ? `/api/deals/${id}/shock`
      : scope === 'portfolio' ? `/api/portfolios/${id}/shock`
      : '/api/portfolios/shock-global'
    const res = await apiFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, data_scope: origin }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur choc')
    if (ticket !== contextVersion) return null
    await loadShockHistory(scope, id)
    return data
  }

  const smileResult = ref(null)
  const smileLoading = ref(false)

  async function runSmileRisk(form) {
    const ticket = contextVersion
    smileLoading.value = true
    smileResult.value = null
    try {
      const url = view.value === 'global'
        ? '/api/portfolios/smile-risk-global'
        : `/api/portfolios/${view.value}/smile-risk`
      const res = await apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, data_scope: dataScope.value }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Erreur du scénario de smile')
      if (ticket !== contextVersion) return null
      smileResult.value = data
      await loadShockHistory(
        view.value === 'global' ? 'smile_global' : 'smile_portfolio',
        view.value === 'global' ? null : view.value,
      )
      return data
    } finally {
      if (ticket === contextVersion) smileLoading.value = false
    }
  }

  // P&L explain waterfall aggregated over the current selection (full
  // reprice chain per deal — slow on a large book, caller shows a spinner).
  async function runPnlExplain(body) {
    const ticket = contextVersion
    const url = view.value === 'global'
      ? '/api/portfolios/pnl-explain-global'
      : `/api/portfolios/${view.value}/pnl-explain`
    const res = await apiFetch(withScope(url), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur P&L explain')
    return ticket === contextVersion ? data : null
  }

  // ── VaR/ES study (async — see core/compute/ and api/var.py) ──────────
  // Launching returns a batch id immediately; nothing actually runs until
  // the compute worker daemon (started separately by Philippe, see
  // backend/scripts/run_compute_worker.py) drains it, so the UI polls
  // GET /var/{id} every few seconds until the batch reaches a terminal
  // status — same status vocabulary as any ComputeBatch (queued/running/
  // completed/completed_with_failures/failed).
  const varStudy = ref(null)
  const varLaunching = ref(false)
  const varPolling = ref(false)
  const varHistory = ref([])
  let varPollTimer = null
  let varGeneration = 0

  function stopVarPolling() {
    varGeneration += 1
    if (varPollTimer) clearTimeout(varPollTimer)
    varPollTimer = null
    varPolling.value = false
  }

  async function pollVarBatch(batchId, ticket = historyToken(), generation = varGeneration) {
    try {
      const res = await apiFetch(`/api/portfolios/var/${batchId}`)
      if (!res.ok) throw await apiError(res, 'Étude VaR indisponible')
      const data = await res.json()
      if (ticket !== historyToken() || generation !== varGeneration) return
      varStudy.value = data
      if (data.status === 'queued' || data.status === 'running') {
        varPollTimer = setTimeout(() => pollVarBatch(batchId, ticket, generation), 3000)
      } else {
        varPolling.value = false
        await loadVarHistory()
      }
    } catch (e) {
      if (ticket === historyToken() && generation === varGeneration) {
        varPolling.value = false
        scopeError.value = e.message
      }
    }
  }

  async function launchVar(form) {
    stopVarPolling()
    const ticket = historyToken()
    const generation = varGeneration
    varLaunching.value = true
    varStudy.value = null
    try {
      const url = view.value === 'global'
        ? '/api/portfolios/var-global'
        : `/api/portfolios/${view.value}/var`
      const res = await apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, data_scope: dataScope.value }),
      })
      const data = await res.json()
      if (!res.ok) {
        const detail = data.detail
        const err = new Error(
          typeof detail === 'object' ? detail.message :
            (detail || 'Erreur au lancement de l\'étude VaR'))
        if (typeof detail === 'object') err.computeDetail = detail
        throw err
      }
      if (ticket !== historyToken() || generation !== varGeneration) return null
      varPolling.value = true
      pollVarBatch(data.batch_id, ticket, generation)
      return data
    } finally {
      if (ticket === historyToken() && generation === varGeneration) varLaunching.value = false
    }
  }

  // History is filtered on frozen origin and portfolio view by the server.
  // Reopening a finished study never needs another calculation.
  async function loadVarHistory() {
    const ticket = historyToken()
    const params = new URLSearchParams({ data_scope: historyScope.value, scope: view.value === 'global' ? 'global' : 'portfolio' })
    if (view.value !== 'global') params.set('portfolio_id', view.value)
    if (historyMode.value === 'ALL_VIEWS') params.set('all_views', 'true')
    const res = await apiFetch(`/api/portfolios/var-history?${params}`)
    if (!res.ok) throw await apiError(res, 'Historique VaR indisponible')
    const rows = await res.json()
    if (ticket === historyToken()) varHistory.value = rows
  }

  function openVarBatch(batchId) {
    stopVarPolling()
    varStudy.value = null
    varPolling.value = true
    pollVarBatch(batchId)
  }

  return {
    portfolios, view, dataScope, historyMode, scopeLabel, historyLabel, scopeError, setDataScope, setHistoryMode,
    valuationDate, risk, riskLoading, exposure, exposureLoading, shockHistory,
    barriers, barriersLoading,
    varStudy, varLaunching, varPolling, varHistory,
    label, isDefaultView, activeDealsCount, members, allMembers, riskMembers,
    currentShockHistory, currentSmileHistory,
    smileResult, smileLoading,
    load, create, rename, remove, assignDeal, setDealPortfolios,
    loadRisk, loadExposure, loadBarriers, selectView, loadShockHistory, runShock, runPnlExplain,
    runSmileRisk, launchVar, loadVarHistory, openVarBatch, stopVarPolling,
  }
})
