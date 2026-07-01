import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { apiFetch } from '../utils/api.js'

const DEFAULT_SCRIPT = `# Autocall Athena 3 ans
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
  PAY KI * WOF`

export const usePricingStore = defineStore('pricing', () => {
  // ── Tabs ──────────────────────────────────────────────────────────
  const leftTab = ref('script')   // 'script' | 'params' | 'deal' | 'events'
  const rightTab = ref('empty')   // 'empty' | 'results' | 'flux' | 'greeks' | 'profile' | 'paths' | 'proba' | 'backtest' | 'mtf' | 'simulation' | 'scenarios'

  // ── Script ────────────────────────────────────────────────────────
  const script = ref(DEFAULT_SCRIPT)
  const scriptParams = ref([])
  const parseError = ref(null)

  // User-edited PARAM values, keyed by name, in display units (e.g. 8 for "8%").
  // Seeded once per name from the script's declared default and never touched
  // again by re-parses — only _syncParamOverrides() (added/removed names) and
  // the user's own typing change it. This is what makes the PARAM inputs
  // "sticky" across script edits instead of snapping back to the script's
  // default on every debounced re-parse.
  const paramOverrides = reactive({})

  function _syncParamOverrides() {
    const names = new Set(scriptParams.value.map(p => p.name))
    for (const k of Object.keys(paramOverrides)) {
      if (!names.has(k)) delete paramOverrides[k]
    }
    for (const p of scriptParams.value) {
      if (!(p.name in paramOverrides)) paramOverrides[p.name] = p.display_default
    }
  }

  // ── CONSTAT (calendrier — mode expert) ──────────────────────────────
  // Same "sticky" pattern as paramOverrides: scriptConstats comes straight
  // from /api/parse (name + kind), constatOverrides holds the actual values
  // the user fills in, seeded once per name and never touched again by a
  // re-parse as long as that name still exists in the script.
  const scriptConstats = ref([])   // [{name, kind: 'single'|'schedule'|'nested_schedule'}]
  const scriptHasStop  = ref(false)
  const constatOverrides = reactive({})

  // frequency/sub_frequency are {value, unit} pairs in the UI (a number input +
  // a D/M/Y select) rather than a single "3M"-style text field — _tenorStr()
  // combines them into the tenor string the backend expects.
  function _defaultConstatValue(kind) {
    if (kind === 'single') return ''
    return reactive({
      start_date: '', end_date: '', roll_date: '',
      frequency: { value: 3, unit: 'M' }, stub: 'short_last',
      sub_frequency: kind === 'nested_schedule' ? { value: 1, unit: 'M' } : null,
    })
  }

  function _tenorStr(t) {
    return (t && t.value) ? `${t.value}${t.unit}` : null
  }

  function _syncConstatOverrides() {
    const names = new Set(scriptConstats.value.map(c => c.name))
    for (const k of Object.keys(constatOverrides)) {
      if (!names.has(k)) delete constatOverrides[k]
    }
    for (const c of scriptConstats.value) {
      if (!(c.name in constatOverrides)) constatOverrides[c.name] = _defaultConstatValue(c.kind)
    }
  }

  // ── Underlyings ───────────────────────────────────────────────────
  const underlyings = ref([
    {
      name: 'Sous-jacent 1', ticker: '', ccy: 'EUR',
      sigma: 20, q: 2.0,
      sigma_fx: 0, rho_sfx: 0, ccyh: 0,
      v0: 4.0, kappa: 2.0, theta: 4.0, xi: 35, rho_h: -70, rho_rS: 40,
      alpha: 20, beta: 50, rho: -30, nu: 40,
      skew: -10, curvature: 5,
      showQuanto: false,
    },
  ])
  const corrMatrix = ref([[1.0]])

  // ── Global params ─────────────────────────────────────────────────
  const globalParams = reactive({
    r: 3.0,
    T: 3.0,
    N: 20000,
    seed: 42,
    model: 'constant',
    antithetic: true,
    deal_ccy: 'EUR',
    value_date: new Date().toISOString().split('T')[0],
    // 'deterministic' (r constant) | 'abm' (gaussien sans retour à la moyenne)
    // | 'hull_white' (gaussien avec retour à la moyenne)
    rateModel: 'deterministic',
    // Défauts non nuls dès qu'un modèle stochastique est sélectionné, pour que
    // l'effet soit visible immédiatement — sigma_r=0 désactiverait tout, quel
    // que soit a_r. 1%/an de vol de taux court et a=0.3 (demi-vie ≈ 2.3 ans)
    // sont des ordres de grandeur réalistes pour un Hull-White EUR/USD.
    sigma_r: 1.5,   // vol du taux court (%/an) — utilisé si rateModel != 'deterministic'
    a_r: 0.3,       // vitesse de retour à la moyenne — utilisé seulement si 'hull_white'
  })

  // ── Yield curve (term structure of zero rates) ────────────────────
  const yieldCurve = reactive({
    enabled: false,
    pillars: [
      { label: '3M',  T: 0.25,  rate: 3.2 },
      { label: '6M',  T: 0.5,   rate: 3.4 },
      { label: '1Y',  T: 1.0,   rate: 3.6 },
      { label: '2Y',  T: 2.0,   rate: 3.8 },
      { label: '3Y',  T: 3.0,   rate: 3.9 },
      { label: '5Y',  T: 5.0,   rate: 4.0 },
      { label: '7Y',  T: 7.0,   rate: 4.1 },
      { label: '10Y', T: 10.0,  rate: 4.2 },
      { label: '15Y', T: 15.0,  rate: 4.25 },
      { label: '20Y', T: 20.0,  rate: 4.3 },
      { label: '30Y', T: 30.0,  rate: 4.35 },
    ],
  })

  // ── Greeks selection ──────────────────────────────────────────────
  const greekSel = reactive({
    delta: true, gamma: false, vega: true,
    theta: true, rho: false, corr: false,
  })
  const selectedGreeks = computed(() => Object.keys(greekSel).filter(k => greekSel[k]))

  // ── Current script DB identity ────────────────────────────────────
  const currentScriptId   = ref(null)
  const currentScriptName = ref('')

  // ── Results & state ───────────────────────────────────────────────
  const result    = ref(null)
  const profile   = ref(null)
  const paths     = ref(null)
  const proba     = ref(null)
  const backtest  = ref(null)
  const mtf       = ref(null)
  const solver    = ref(null)
  const grid      = ref(null)
  const scenarios = ref(null)
  const loading   = ref(false)
  const error     = ref(null)
  const progress  = ref(0)

  let _progressTimer = null

  function _startProgress(estimatedMs) {
    progress.value = 0
    clearInterval(_progressTimer)
    const step = 80 / (estimatedMs / 80)
    _progressTimer = setInterval(() => {
      if (progress.value < 90) progress.value = Math.min(90, progress.value + step)
    }, 80)
  }

  function _stopProgress() {
    clearInterval(_progressTimer)
    progress.value = 100
    setTimeout(() => { progress.value = 0 }, 600)
  }

  // ── Helpers ───────────────────────────────────────────────────────
  function _buildUserParams() {
    const up = {}
    for (const p of scriptParams.value) {
      const v = paramOverrides[p.name] ?? p.raw_default
      up[p.name] = p.is_pct ? v / 100 : v
    }
    return up
  }

  function _buildUls() {
    return underlyings.value.map(u => ({
      name: u.name, ticker: u.ticker, ccy: u.ccy,
      sigma: u.sigma / 100,
      q: u.q / 100,
      sigma_fx: u.sigma_fx / 100,
      rho_sfx: u.rho_sfx / 100,
      ccyh: u.ccyh / 10000,
      v0: u.v0 / 100,
      kappa: u.kappa,
      theta: u.theta / 100,
      xi: u.xi / 100,
      rho_h: u.rho_h / 100,
      rho_rS: u.rho_rS / 100,
      alpha: u.alpha / 100,
      beta: u.beta / 100,
      rho: u.rho / 100,
      nu: u.nu / 100,
      skew: u.skew / 100,
      curvature: u.curvature / 100,
    }))
  }

  function _buildCorr() {
    const n = underlyings.value.length
    return Array.from({ length: n }, (_, i) =>
      Array.from({ length: n }, (_, j) =>
        i === j ? 1.0 : (corrMatrix.value[i]?.[j] ?? 0.0)
      )
    )
  }

  // Converts constatOverrides into the {name: values} shape resolve_constats()
  // expects on the backend — combining each {value,unit} pair back into a
  // tenor string ("3M") only at the point of sending, so the UI can keep them
  // as two separate, simple inputs.
  function _buildConstats() {
    const out = {}
    for (const c of scriptConstats.value) {
      const v = constatOverrides[c.name]
      if (c.kind === 'single') {
        out[c.name] = v
      } else {
        out[c.name] = {
          start_date: v.start_date, end_date: v.end_date, roll_date: v.roll_date,
          frequency: _tenorStr(v.frequency), stub: v.stub,
          sub_frequency: c.kind === 'nested_schedule' ? _tenorStr(v.sub_frequency) : null,
        }
      }
    }
    return out
  }

  function _baseBody() {
    return {
      script: script.value,
      underlyings: _buildUls(),
      corr_matrix: _buildCorr(),
      r: globalParams.r / 100,
      T: globalParams.T,
      seed: globalParams.seed,
      model: globalParams.model,
      user_params: _buildUserParams(),
      yield_curve: yieldCurve.enabled
        ? yieldCurve.pillars.map(p => [p.T, p.rate / 100])
        : [],
      constats: _buildConstats(),
    }
  }

  // sigma_r/a_r only apply to /price (and Greeks) — see runPricing/runGreeks.
  // Derives the two backend params from the single rateModel selector so
  // switching back to "Déterministe" always sends 0 regardless of leftover
  // field values, and "ABM" always sends a_r=0 (no mean reversion).
  function _rateParams() {
    if (globalParams.rateModel === 'deterministic') return { sigma_r: 0, a_r: 0 }
    if (globalParams.rateModel === 'abm') return { sigma_r: globalParams.sigma_r / 100, a_r: 0 }
    return { sigma_r: globalParams.sigma_r / 100, a_r: globalParams.a_r }   // hull_white
  }

  // ── Parse ─────────────────────────────────────────────────────────
  async function parseScript() {
    if (!script.value.trim()) {
      scriptParams.value = []; scriptConstats.value = []; parseError.value = null
      _syncParamOverrides(); _syncConstatOverrides()
      return
    }
    try {
      const res = await fetch('/api/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: script.value }),
      })
      const data = await res.json()
      if (data.ok) {
        scriptParams.value = data.params; scriptConstats.value = data.constats || []
        scriptHasStop.value = data.has_stop ?? false
        parseError.value = null
      } else {
        parseError.value = data.errors; scriptParams.value = []; scriptConstats.value = []
        scriptHasStop.value = false
      }
      _syncParamOverrides(); _syncConstatOverrides()
    } catch (e) { parseError.value = e.message }
  }

  // Snapshot of the inputs that actually produced a pricing run, captured at
  // run time so the "Résultats" summary stays accurate even if the user keeps
  // editing params afterward — it describes THIS price, not the current form.
  function _snapshotInputs() {
    return {
      underlyings: underlyings.value.map(u => ({
        name: u.name, ticker: u.ticker, ccy: u.ccy, sigma: u.sigma, q: u.q, rho_rS: u.rho_rS,
      })),
      corrMatrix: corrMatrix.value.map(row => [...row]),
      r: globalParams.r, T: globalParams.T, N: globalParams.N, seed: globalParams.seed,
      model: globalParams.model, antithetic: globalParams.antithetic,
      rateModel: globalParams.rateModel, sigma_r: globalParams.sigma_r, a_r: globalParams.a_r,
      yieldCurveEnabled: yieldCurve.enabled,
      paramsUsed: scriptParams.value.map(p => ({
        name: p.name, value: paramOverrides[p.name] ?? p.raw_default, is_pct: p.is_pct,
      })),
      hasConstats: scriptConstats.value.length > 0,
      hasStop: scriptHasStop.value,
      yieldCurvePillars: yieldCurve.enabled
        ? yieldCurve.pillars.map(p => ({ T: p.T, rate: p.rate, label: p.label }))
        : [],
    }
  }

  // ── Price ─────────────────────────────────────────────────────────
  async function runPricing() {
    loading.value = true; error.value = null; result.value = null
    _startProgress((globalParams.N / 20000) * 350)
    try {
      const res = await fetch('/api/price', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ..._baseBody(),
          N: globalParams.N,
          antithetic: globalParams.antithetic,
          compute_greeks: false,
          selected_greeks: selectedGreeks.value,
          ..._rateParams(),
        }),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur serveur' }
      else { result.value = { ...(await res.json()), _inputs: _snapshotInputs() }; rightTab.value = 'results' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Greeks ────────────────────────────────────────────────────────
  async function runGreeks() {
    if (!result.value || !selectedGreeks.value.length) return
    loading.value = true; error.value = null
    _startProgress(selectedGreeks.value.length * (globalParams.N / 20000) * 400)
    try {
      const res = await fetch('/api/price', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ..._baseBody(),
          N: globalParams.N,
          antithetic: globalParams.antithetic,
          compute_greeks: true,
          selected_greeks: selectedGreeks.value,
          ..._rateParams(),
        }),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur serveur' }
      else {
        const data = await res.json()
        result.value = { ...result.value, greeks: data.greeks }
        rightTab.value = 'greeks'
      }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Payoff Profile ────────────────────────────────────────────────
  async function runProfile() {
    loading.value = true; error.value = null
    _startProgress(800)
    try {
      const res = await fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(_baseBody()),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur' }
      else { profile.value = await res.json(); rightTab.value = 'profile' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── MC Paths ──────────────────────────────────────────────────────
  async function runPaths() {
    loading.value = true; error.value = null
    _startProgress(1500)
    try {
      const res = await fetch('/api/paths', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ..._baseBody(), N_stat: 500, N_display: 50 }),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur' }
      else { paths.value = await res.json(); rightTab.value = 'paths' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Probability analysis ──────────────────────────────────────────
  async function runProba() {
    loading.value = true; error.value = null
    _startProgress(2000)
    try {
      const res = await fetch('/api/proba', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ..._baseBody(), N: 5000 }),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur' }
      else { proba.value = await res.json(); rightTab.value = 'proba' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Historical backtest ───────────────────────────────────────────
  async function runBacktest(params = {}) {
    loading.value = true; error.value = null
    _startProgress(8000)
    try {
      const res = await fetch('/api/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ..._baseBody(),
          start_date: params.start_date || '2010-01-01',
          end_date: params.end_date || null,
          freq: params.freq || 21,
          invest_pct: params.invest_pct || (result.value ? result.value.price * 100 : 100),
          rf_rate: params.rf_rate || 2.0,
        }),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur' }
      else { backtest.value = await res.json(); rightTab.value = 'backtest' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Mark to Future (nested Monte Carlo) ────────────────────────────
  async function runMtf(params = {}) {
    if (!result.value) { error.value = 'Lancez d\'abord un pricing (▶ Pricer).'; return }
    const n_outer = params.n_outer || 200
    const n_inner = params.n_inner || 500
    const n_dates = params.n_dates || 5
    loading.value = true; error.value = null
    // Rough cost calibration: ~4.7s for the 200×500×5 default on a GBM/local-vol model.
    _startProgress((n_outer * n_inner * n_dates / 500000) * 4700)
    try {
      const res = await fetch('/api/mtf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ..._baseBody(),
          main_price: result.value.price * 100,
          n_outer, n_inner, n_dates,
          seed: params.seed || globalParams.seed,
        }),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur serveur' }
      else { mtf.value = await res.json(); rightTab.value = 'mtf' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Simulation: PARAM solver + 2D price grid ───────────────────────
  // Script PARAMs declared as "8%" are stored server-side as a fraction (0.08).
  // These helpers convert between that stored unit and the % the UI displays,
  // using the is_pct flag already returned by /api/parse for each PARAM.
  function paramIsPct(name) {
    return scriptParams.value.find(p => p.name === name)?.is_pct ?? false
  }
  function toStoredUnits(name, displayVal) {
    return paramIsPct(name) ? displayVal / 100 : displayVal
  }
  function fromStoredUnits(name, storedVal) {
    return paramIsPct(name) ? storedVal * 100 : storedVal
  }

  async function runSolver({ param_name, target_price_pct, lo, hi, N, tol, max_iter }) {
    loading.value = true; error.value = null
    _startProgress((N || 8000) / 8000 * ((max_iter || 40) / 40) * 1500)
    try {
      const res = await fetch('/api/solve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ..._baseBody(),
          param_name,
          target_price: target_price_pct / 100,
          lo: toStoredUnits(param_name, lo),
          hi: toStoredUnits(param_name, hi),
          N: N || 8000, tol: tol || 1e-4, max_iter: max_iter || 40,
        }),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur serveur' }
      else { solver.value = await res.json(); rightTab.value = 'simulation' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  async function runGrid({ param_x, x_min, x_max, x_steps, param_y, y_min, y_max, y_steps, N }) {
    loading.value = true; error.value = null
    _startProgress((N || 4000) * (x_steps || 9) * (y_steps || 9) / (4000 * 81) * 3000)
    try {
      const res = await fetch('/api/grid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ..._baseBody(),
          param_x, x_min: toStoredUnits(param_x, x_min), x_max: toStoredUnits(param_x, x_max),
          x_steps: x_steps || 9,
          param_y, y_min: toStoredUnits(param_y, y_min), y_max: toStoredUnits(param_y, y_max),
          y_steps: y_steps || 9,
          N: N || 4000,
        }),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur serveur' }
      else { grid.value = await res.json(); rightTab.value = 'simulation' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Scenarios: spot x vol stress grid ──────────────────────────────
  // spot_shocks_pct/vol_shocks_pct are plain percentages from the UI (e.g. -10
  // for -10% spot, 5 for +5pp vol) — divided by 100 here to match the stored
  // fraction units run_mc expects (spot_mult/vol_add).
  async function runScenarios({ spot_shocks_pct, vol_shocks_pct, N }) {
    loading.value = true; error.value = null
    const cells = (spot_shocks_pct.length || 9) * (vol_shocks_pct.length || 5)
    _startProgress(cells * (N || 2000) / (45 * 2000) * 3000)
    try {
      const res = await fetch('/api/scenarios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ..._baseBody(),
          spot_shocks: spot_shocks_pct.map(v => v / 100),
          vol_shocks: vol_shocks_pct.map(v => v / 100),
          N: N || 2000,
        }),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur serveur' }
      else { scenarios.value = await res.json(); rightTab.value = 'scenarios' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Schedule (CONSTAT calendar) preview ─────────────────────────────
  // Pure API call, no shared state mutation — each CONSTAT sub-panel in
  // PayScriptEditor.vue manages its own preview result locally, so multiple
  // CONSTAT()/CONSTAT()() declarations in the same script don't clobber a
  // single shared ref, and this doesn't touch the main loading/progress UI.
  async function fetchSchedulePreview({ start_date, end_date, roll_date, frequency, stub, sub_frequency }) {
    const res = await fetch('/api/schedule/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_date, end_date, roll_date, frequency, stub,
        sub_frequency: sub_frequency || null,
      }),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Erreur serveur')
    }
    return res.json()
  }

  // ── Yahoo Finance data loader ─────────────────────────────────────
  const yfStatus = ref('')

  async function loadYfOne(idx) {
    const u = underlyings.value[idx]
    if (!u || !u.ticker?.trim()) { yfStatus.value = '⚠ Entrez un ticker (ex: ^STOXX50E)'; return }
    const tk = u.ticker.trim().toUpperCase()
    underlyings.value[idx].ticker = tk   // normalise en place
    yfStatus.value = `Chargement ${tk}…`
    try {
      const res = await fetch(`/api/finance/hist_vol?tickers=${encodeURIComponent(tk)}&period=1y`)
      const data = await res.json()
      if (data.error) { yfStatus.value = `⚠ ${tk}: ${data.error}`; return }
      // backend renvoie la clé uppercase identique à tk
      const vol = data.vols?.[tk] ?? null
      const q   = data.div_yields?.[tk] ?? 0
      if (vol != null) {
        underlyings.value[idx].sigma = Math.round(vol * 1000) / 10
        underlyings.value[idx].alpha = Math.round(vol * 1000) / 10
        underlyings.value[idx].q     = Math.round(q * 10000) / 100
        underlyings.value[idx].name  = tk
        yfStatus.value = `✓ ${tk} — σ=${(vol*100).toFixed(1)}%, q=${(q*100).toFixed(2)}% · ${data.n_obs} obs.`
      } else {
        yfStatus.value = `⚠ ${tk}: introuvable sur Yahoo Finance`
        if (data.missing?.includes(tk)) yfStatus.value += ' — vérifiez le ticker'
      }
    } catch (e) { yfStatus.value = '⚠ Erreur réseau: ' + e.message }
  }

  async function loadYfAll() {
    // Normalise tickers uppercase avant envoi
    underlyings.value.forEach(u => { if (u.ticker) u.ticker = u.ticker.trim().toUpperCase() })
    const pairs = underlyings.value.map((u, i) => ({ u, idx: i, tick: u.ticker })).filter(p => p.tick)
    if (!pairs.length) { yfStatus.value = '⚠ Aucun ticker renseigné'; return }
    yfStatus.value = 'Téléchargement en cours…'
    const tickers = pairs.map(p => p.tick)
    try {
      const res = await fetch(`/api/finance/hist_vol?tickers=${encodeURIComponent(tickers.join(','))}&period=1y`)
      const data = await res.json()
      if (data.error) { yfStatus.value = '⚠ ' + data.error; return }

      pairs.forEach(({ u, idx, tick }) => {
        const vol = data.vols?.[tick] ?? null
        if (vol == null) return
        const q = data.div_yields?.[tick] ?? 0
        underlyings.value[idx].sigma = Math.round(vol * 1000) / 10
        underlyings.value[idx].alpha = Math.round(vol * 1000) / 10
        underlyings.value[idx].q     = Math.round(q * 10000) / 100
        underlyings.value[idx].name  = tick
      })

      // Apply correlation matrix
      const n = underlyings.value.length
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        const ti = pairs[i]?.tick, tj = pairs[j]?.tick
        if (i !== j && ti && tj && data.corr[ti]?.[tj] !== undefined) {
          if (!corrMatrix.value[i]) corrMatrix.value[i] = []
          corrMatrix.value[i][j] = parseFloat(data.corr[ti][tj].toFixed(4))
        }
      }

      const fnd = data.tickers.join(', ')
      const miss = data.missing?.length ? ` ⚠ Introuvables: ${data.missing.join(', ')}` : ''
      yfStatus.value = `✓ ${fnd} — σ, q, corr mis à jour · ${data.n_obs} obs.${miss}`
    } catch (e) { yfStatus.value = '⚠ Erreur: ' + e.message }
  }

  // ── Underlyings management ────────────────────────────────────────
  // ── Reset / Load from DB ──────────────────────────────────────────
  function _defaultUnderlying(n) {
    return {
      name: `Sous-jacent ${n}`, ticker: '', ccy: 'EUR',
      sigma: 20, q: 2.0, sigma_fx: 0, rho_sfx: 0, ccyh: 0,
      v0: 4.0, kappa: 2.0, theta: 4.0, xi: 35, rho_h: -70, rho_rS: 40,
      alpha: 20, beta: 50, rho: -30, nu: 40,
      skew: -10, curvature: 5, showQuanto: false,
    }
  }

  function _clearResults() {
    result.value = null; profile.value = null; paths.value = null
    proba.value = null; backtest.value = null; mtf.value = null
    solver.value = null; grid.value = null; scenarios.value = null
    rightTab.value = 'empty'
  }

  function resetToDefaults() {
    currentScriptId.value   = null
    currentScriptName.value = ''
    script.value = DEFAULT_SCRIPT
    underlyings.value = [_defaultUnderlying(1)]
    corrMatrix.value  = [[1.0]]
    Object.assign(globalParams, {
      r: 3.0, T: 3.0, N: 20000, seed: 42, model: 'constant',
      antithetic: true, deal_ccy: 'EUR', rateModel: 'deterministic',
      sigma_r: 1.5, a_r: 0.3,
      value_date: new Date().toISOString().split('T')[0],
    })
    yieldCurve.enabled = false
    _clearResults()
    parseScript()
  }

  async function loadFromDb(data) {
    currentScriptId.value   = data.id
    currentScriptName.value = data.name
    script.value = data.script_text
    await parseScript()

    if (data.params_json) {
      const saved = JSON.parse(data.params_json)
      for (const [k, v] of Object.entries(saved)) {
        if (k in paramOverrides) paramOverrides[k] = v
      }
    }

    if (data.constats_json) {
      const saved = JSON.parse(data.constats_json)
      for (const [k, v] of Object.entries(saved)) {
        if (!(k in constatOverrides)) continue
        if (typeof v === 'string') {
          constatOverrides[k] = v
        } else if (v && typeof v === 'object') {
          const ov = constatOverrides[k]
          if (ov && typeof ov === 'object') {
            ov.start_date = v.start_date || ''
            ov.end_date   = v.end_date   || ''
            ov.roll_date  = v.roll_date  || ''
            ov.stub       = v.stub       || 'short_last'
            if (v.frequency && ov.frequency) {
              if (typeof v.frequency === 'object') {
                ov.frequency.value = v.frequency.value ?? 3
                ov.frequency.unit  = v.frequency.unit  ?? 'M'
              } else {
                const m = String(v.frequency).match(/^(\d+)([DWMY])$/i)
                if (m) { ov.frequency.value = parseInt(m[1]); ov.frequency.unit = m[2].toUpperCase() }
              }
            }
            if (v.sub_frequency && ov.sub_frequency) {
              if (typeof v.sub_frequency === 'object') {
                ov.sub_frequency.value = v.sub_frequency.value ?? 1
                ov.sub_frequency.unit  = v.sub_frequency.unit  ?? 'M'
              } else {
                const m = String(v.sub_frequency).match(/^(\d+)([DWMY])$/i)
                if (m) { ov.sub_frequency.value = parseInt(m[1]); ov.sub_frequency.unit = m[2].toUpperCase() }
              }
            }
          }
        }
      }
    }

    if (data.global_params_json) {
      const saved = JSON.parse(data.global_params_json)
      for (const [k, v] of Object.entries(saved)) {
        if (k in globalParams) globalParams[k] = v
      }
    }

    _clearResults()
  }

  function _scriptBody() {
    return {
      script_text: script.value,
      params_json: JSON.stringify({ ...paramOverrides }),
      constats_json: JSON.stringify(JSON.parse(JSON.stringify(constatOverrides))),
      global_params_json: JSON.stringify({
        r: globalParams.r, T: globalParams.T, N: globalParams.N,
        seed: globalParams.seed, model: globalParams.model,
        antithetic: globalParams.antithetic, deal_ccy: globalParams.deal_ccy,
        rateModel: globalParams.rateModel, sigma_r: globalParams.sigma_r, a_r: globalParams.a_r,
        value_date: globalParams.value_date,
      }),
    }
  }

  async function saveScript({ name, description = '', folderId = null, isShared = false, tags = '' }) {
    const res = await apiFetch('/api/db/scripts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description, folder_id: folderId, is_shared: isShared, tags, ..._scriptBody() }),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur sauvegarde') }
    const saved = await res.json()
    currentScriptId.value   = saved.id
    currentScriptName.value = saved.name
    return saved
  }

  async function updateScript(patch = {}) {
    if (!currentScriptId.value) throw new Error('Aucun script courant')
    const res = await apiFetch(`/api/db/scripts/${currentScriptId.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...patch, ..._scriptBody() }),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur mise à jour') }
    const updated = await res.json()
    currentScriptName.value = updated.name ?? currentScriptName.value
    return updated
  }

  function addUnderlying() {
    const n = underlyings.value.length
    underlyings.value.push({
      name: `Sous-jacent ${n+1}`, ticker: '', ccy: 'EUR',
      sigma: 20, q: 2.0, sigma_fx: 0, rho_sfx: 0, ccyh: 0,
      v0: 4.0, kappa: 2.0, theta: 4.0, xi: 35, rho_h: -70, rho_rS: 40,
      alpha: 20, beta: 50, rho: -30, nu: 40,
      skew: -10, curvature: 5, showQuanto: false,
    })
    const m = corrMatrix.value
    m.forEach(row => row.push(0))
    m.push(new Array(n+1).fill(0))
    m[n][n] = 1
  }

  function removeUnderlying(i) {
    if (underlyings.value.length <= 1) return
    underlyings.value.splice(i, 1)
    corrMatrix.value.splice(i, 1)
    corrMatrix.value.forEach(row => row.splice(i, 1))
  }

  return {
    leftTab, rightTab,
    script, scriptParams, parseError, paramOverrides, scriptConstats, constatOverrides, scriptHasStop,
    underlyings, corrMatrix,
    globalParams, yieldCurve, greekSel, selectedGreeks,
    result, profile, paths, proba, backtest, mtf, solver, grid, scenarios,
    loading, error, progress, yfStatus,
    currentScriptId, currentScriptName,
    parseScript, runPricing, runGreeks,
    runProfile, runPaths, runProba, runBacktest, runMtf,
    runSolver, runGrid, paramIsPct, fromStoredUnits, runScenarios, fetchSchedulePreview,
    loadYfOne, loadYfAll,
    addUnderlying, removeUnderlying,
    resetToDefaults, loadFromDb, saveScript, updateScript,
    pricingBody: () => ({ ..._baseBody(), N: globalParams.N, antithetic: globalParams.antithetic, ..._rateParams() }),
  }
})
