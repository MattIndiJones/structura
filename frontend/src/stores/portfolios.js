import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { apiFetch } from '../utils/api.js'
import { useDealsStore } from './deals.js'

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
  const view = ref('global')            // 'global' | portfolio id
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

  const activeDealsCount = computed(() =>
    dealsStore.deals.filter(d => d.status === 'actif').length)

  const members = computed(() => {
    if (view.value === 'global') return dealsStore.deals.filter(d => d.status === 'actif')
    return dealsStore.deals.filter(d => d.status === 'actif' && d.portfolio_id === view.value)
  })

  async function load() {
    const res = await apiFetch('/api/portfolios')
    portfolios.value = await res.json()
  }

  async function create(name) {
    await apiFetch('/api/portfolios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    await load()
  }

  async function rename(p, name) {
    await apiFetch(`/api/portfolios/${p.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    await load()
  }

  async function remove(p) {
    await apiFetch(`/api/portfolios/${p.id}`, { method: 'DELETE' })
    if (view.value === p.id) view.value = 'global'
    await dealsStore.loadDeals()
    await load()
    await loadRisk()
  }

  async function assignDeal(dealId, rawValue) {
    await apiFetch(`/api/deals/${dealId}/portfolio`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ portfolio_id: Number(rawValue) }),
    })
    await dealsStore.loadDeals()
    await load()
    if (risk.value) await loadRisk()
  }

  async function loadRisk() {
    riskLoading.value = true
    try {
      const url = view.value === 'global'
        ? '/api/portfolios/risk-global'
        : `/api/portfolios/${view.value}/risk`
      const res = await apiFetch(url)
      risk.value = await res.json()
    } finally {
      riskLoading.value = false
    }
  }

  async function loadExposure() {
    exposureLoading.value = true
    try {
      const url = view.value === 'global'
        ? '/api/portfolios/exposure-by-counterparty'
        : `/api/portfolios/${view.value}/exposure-by-counterparty`
      const res = await apiFetch(url)
      exposure.value = await res.json()
    } finally {
      exposureLoading.value = false
    }
  }

  // Barrier proximity — unlike loadRisk/loadExposure (cheap reads over
  // already-persisted data), this calls out to live market data per deal
  // (backend's build_watchlist_row, no caching) so it is NOT auto-loaded on
  // every portfolio switch — only when the Barrières tab is actually opened
  // (see RiskManagementView.vue), same "expensive, explicit" treatment as
  // the VaR study and P&L explain below.
  const barriers = ref(null)
  const barriersLoading = ref(false)

  async function loadBarriers() {
    barriersLoading.value = true
    try {
      const url = view.value === 'global'
        ? '/api/portfolios/barriers-global'
        : `/api/portfolios/${view.value}/barriers`
      const res = await apiFetch(url)
      barriers.value = await res.json()
    } finally {
      barriersLoading.value = false
    }
  }

  function selectView(v) {
    view.value = v
    loadRisk()
    loadExposure()
    loadShockHistory(v === 'global' ? 'global' : 'portfolio', v === 'global' ? null : v)
    // Barrières is lazy (see loadBarriers) — just drop the stale scope's
    // result so the tab shows a fresh "à charger" state, not another
    // portfolio's rows, if it's already been opened once.
    barriers.value = null
  }

  // History keys: a bare deal id for deal scope, '<scope>:<id or empty>'
  // otherwise ('global:' for the whole book) — same convention as the
  // /api/shocks query parameters.
  function historyKey(scope, id) {
    return scope === 'deal' ? id : `${scope}:${id ?? ''}`
  }

  async function loadShockHistory(scope, id) {
    const params = scope === 'deal' ? `deal_id=${id}` : (id ? `portfolio_id=${id}` : 'scope=global')
    const res = await apiFetch(`/api/shocks?${params}&limit=5`)
    shockHistory[historyKey(scope, id)] = await res.json()
  }

  const currentShockHistory = computed(() => {
    const key = view.value === 'global' ? 'global:' : `portfolio:${view.value}`
    return shockHistory[key] || []
  })

  async function runShock(scope, id, form) {
    const url = scope === 'deal' ? `/api/deals/${id}/shock`
      : scope === 'portfolio' ? `/api/portfolios/${id}/shock`
      : '/api/portfolios/shock-global'
    const res = await apiFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur choc')
    await loadShockHistory(scope, id)
    return data
  }

  // P&L explain waterfall aggregated over the current selection (full
  // reprice chain per deal — slow on a large book, caller shows a spinner).
  async function runPnlExplain(body) {
    const url = view.value === 'global'
      ? '/api/portfolios/pnl-explain-global'
      : `/api/portfolios/${view.value}/pnl-explain`
    const res = await apiFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Erreur P&L explain')
    return data
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

  function stopVarPolling() {
    if (varPollTimer) clearTimeout(varPollTimer)
    varPollTimer = null
    varPolling.value = false
  }

  async function pollVarBatch(batchId) {
    const res = await apiFetch(`/api/portfolios/var/${batchId}`)
    const data = await res.json()
    varStudy.value = data
    if (data.status === 'queued' || data.status === 'running') {
      varPollTimer = setTimeout(() => pollVarBatch(batchId), 3000)
    } else {
      varPolling.value = false
      loadVarHistory()
    }
  }

  async function launchVar(form) {
    stopVarPolling()
    varLaunching.value = true
    varStudy.value = null
    try {
      const url = view.value === 'global'
        ? '/api/portfolios/var-global'
        : `/api/portfolios/${view.value}/var`
      const res = await apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Erreur au lancement de l\'étude VaR')
      varPolling.value = true
      pollVarBatch(data.batch_id)
      return data
    } finally {
      varLaunching.value = false
    }
  }

  // Past studies (any status) — reuses the generic compute batches list,
  // filtered client-side to this one kind, so reopening a finished study
  // never needs re-running it.
  async function loadVarHistory() {
    const res = await apiFetch('/api/compute/batches')
    const all = await res.json()
    varHistory.value = all.filter(b => b.kind === 'var_scenario').slice(0, 10)
  }

  function openVarBatch(batchId) {
    stopVarPolling()
    varStudy.value = null
    varPolling.value = true
    pollVarBatch(batchId)
  }

  return {
    portfolios, view, risk, riskLoading, exposure, exposureLoading, shockHistory,
    barriers, barriersLoading,
    varStudy, varLaunching, varPolling, varHistory,
    label, isDefaultView, activeDealsCount, members, currentShockHistory,
    load, create, rename, remove, assignDeal,
    loadRisk, loadExposure, loadBarriers, selectView, loadShockHistory, runShock, runPnlExplain,
    launchVar, loadVarHistory, openVarBatch, stopVarPolling,
  }
})
