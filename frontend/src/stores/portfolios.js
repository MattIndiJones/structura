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
  { label: 'Crise systémique', spot_shock_pct: -30, vol_shock_pts: 20, rate_shock_bp: -100, corr_shock_pts: 20 },
]

export function blankShockForm() {
  return { spot_shock_pct: 0, vol_shock_pts: 0, rate_shock_bp: 0, corr_shock_pts: 0 }
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

  function selectView(v) {
    view.value = v
    loadRisk()
    loadShockHistory(v === 'global' ? 'global' : 'portfolio', v === 'global' ? null : v)
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

  return {
    portfolios, view, risk, riskLoading, shockHistory,
    label, isDefaultView, activeDealsCount, members, currentShockHistory,
    load, create, rename, remove, assignDeal,
    loadRisk, selectView, loadShockHistory, runShock, runPnlExplain,
  }
})
