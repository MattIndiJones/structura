import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { apiFetch } from '../utils/api.js'

const DEFAULT_SCRIPT = `# Autocall Athena 3 ans
PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`

export const usePricingStore = defineStore('pricing', () => {
  // ── Tabs ──────────────────────────────────────────────────────────
  const leftTab = ref('script')   // 'script' | 'params' | 'deal' | 'events'
  const rightTab = ref('empty')   // 'empty' | 'results' | 'flux' | 'greeks' | 'profile' | 'paths' | 'proba' | 'backtest' | 'mtf' | 'simulation' | 'scenarios' | 'kid' | 'emt'

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
      if (!(p.name in paramOverrides)) {
        // PARAM() → a table of per-observation rows, seeded with one row
        // (the script's optional seed). One row = constant across all
        // observations (the engine extends the last row), so this initial
        // state is immediately priceable.
        paramOverrides[p.name] = p.kind === 'array' ? [p.display_default] : p.display_default
      } else if (p.kind === 'array' && !Array.isArray(paramOverrides[p.name])) {
        // Declaration changed PARAM → PARAM() under a sticky override:
        // promote the scalar to a single-row table instead of crashing the UI.
        paramOverrides[p.name] = [paramOverrides[p.name]]
      } else if (p.kind !== 'array' && Array.isArray(paramOverrides[p.name])) {
        paramOverrides[p.name] = paramOverrides[p.name][0] ?? p.display_default
      }
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
      dividendCurveEnabled: false, dividendDecay: 10.0,
      sigma_fx: 0, rho_sfx: 0, ccyh: 0,
      v0: 4.0, kappa: 2.0, theta: 4.0, xi: 35, rho_h: -70, rho_rS: 40,
      alpha: 20, beta: 50, rho: -30, nu: 40,
      skew: -10, curvature: 5,
      showQuanto: false,
    },
  ])
  const corrMatrix = ref([[1.0]])
  // Which underlying is being shown/edited — shared between the Deal tab
  // (ticker picker) and Marché & Paramètres (market-data calibration) so
  // switching the active name in one is reflected in the other.
  const activeUnderlyingIdx = ref(0)

  // ── Global params ─────────────────────────────────────────────────
  const globalParams = reactive({
    r: 3.0,
    T: 3.0,
    N: 20000,
    seed: 42,
    model: 'constant',
    antithetic: true,
    deal_ccy: 'EUR',
    trade_date: new Date().toISOString().split('T')[0],
    strike_date: new Date().toISOString().split('T')[0],
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
    // 'weekly' (extrema aux pas hebdomadaires de la grille MC, historique)
    // | 'continuous' (pont brownien intra-pas : WOF_MIN/S_MIN/BOF_MAX reflètent
    // le chemin continu — P(KI) plus élevée, jambe put mieux valorisée)
    barrierMonitoring: 'weekly',
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

  // ── Pre-trade opportunity (Indicative) this pricing session is tied to —
  // created lazily on first KID/EMT save, reused for every save after that
  // until reset. See db/models.py:Indicative for the full rationale. ──────
  const currentIndicativeId = ref(null)

  // RFQ this pricing session was pre-filled from (see loadFromRfq below) —
  // sent as Deal.rfq_id at booking time so the winning quote's RFQ can be
  // traced back from the deal, and so book_deal can close out that RFQ.
  const currentRfqId = ref(null)
  // One-shot handoff to DealTab.vue's form (contrepartie/price_traded from
  // the RFQ's selected quote) — consumed and cleared on mount, since those
  // fields live in the component, not the store.
  const pendingDealPrefill = ref(null)
  // Booked deal this session was reopened from (loadFromDeal). Its commercial
  // terms are NOT the store's — they live in DealTab's form — so reopening a
  // deal has to hand them over through pendingDealPrefill like the RFQ path
  // does. Also what tells DealTab this deal already exists: booking again
  // from here would silently create a duplicate under a new reference.
  const openedDeal = ref(null)

  // Product title from the script's leading "# comment" line — shared by
  // KidPanel/EmtPanel save actions and the EMT print view.
  const productTitle = computed(() => {
    const m = script.value.match(/^\s*#\s*(.+)$/m)
    return m ? m[1].trim() : 'Produit structuré'
  })

  async function ensureIndicative() {
    if (currentIndicativeId.value) return currentIndicativeId.value
    const res = await apiFetch('/api/indicatives', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contrepartie: '',
        devise: globalParams.deal_ccy || 'EUR',
        nominal: 0,
        underlyings: underlyings.value.map(u => ({ name: u.name, ticker: u.ticker })),
        script_snapshot: script.value,
        script_id: currentScriptId.value || null,
        market_snapshot: { r: globalParams.r, T: globalParams.T, model: globalParams.model },
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Erreur création fiche indicative')
    }
    const ind = await res.json()
    currentIndicativeId.value = ind.id
    return ind.id
  }

  // ── Results & state ───────────────────────────────────────────────
  const result    = ref(null)
  const profile   = ref(null)
  const paths     = ref(null)
  const proba     = ref(null)
  const backtest  = ref(null)
  const mtf       = ref(null)
  // Assistant de scripting IA. `scriptGen` porte le script proposé, sa
  // reformulation en français et sa fiche de contrôle — jamais appliqué
  // automatiquement : c'est l'utilisateur qui adopte.
  const scriptGen        = ref(null)
  const scriptGenLoading = ref(false)
  const scriptGenError   = ref(null)
  const scriptProviders  = ref(null)
  // Corps de requête ayant produit `mtf`, rejoué à l'identique par le drill-down.
  const mtfBody   = ref(null)
  const mtfDrill  = ref(null)
  const mtfDrillLoading = ref(false)
  const mtfDrillError   = ref(null)
  const solver    = ref(null)
  const grid      = ref(null)
  const scenarios = ref(null)
  const kid       = ref(null)
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
      if (Array.isArray(v)) {
        // PARAM() rows, display → stored units per row; blank rows dropped.
        // Empty table → fall back to the seed so pricing stays possible.
        const rows = v.filter(x => x !== '' && x != null && !isNaN(x))
          .map(x => p.is_pct ? x / 100 : x)
        up[p.name] = rows.length ? rows : [p.is_pct ? p.raw_default / 100 : p.raw_default]
      } else {
        up[p.name] = p.is_pct ? v / 100 : v
      }
    }
    return up
  }

  function _buildUls() {
    return underlyings.value.map(u => ({
      name: u.name, ticker: u.ticker, ccy: u.ccy,
      sigma: u.sigma / 100,
      q: u.q / 100,
      dividend_curve: _buildDividendCurve(u).map(p => [p.T, p.rate / 100]),
      dividend_decay: u.dividendCurveEnabled
        ? Math.max(0, Math.min(100, Number(u.dividendDecay) || 0)) / 100
        : 0,
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

  function _buildDividendCurve(u) {
    if (!u?.dividendCurveEnabled) return []
    const q1 = Math.max(0, Number(u.q) || 0)
    const decay = Math.max(0, Math.min(100, Number(u.dividendDecay) || 0)) / 100
    const years = Math.max(1, Math.ceil(Number(globalParams.T) || 1))
    return Array.from({ length: years }, (_, index) => ({
      label: `A${index + 1}`,
      T: index + 1,
      rate: q1 * Math.pow(1 - decay, index),
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

  // Mirrors _buildConstats()'s output shape back into constatOverrides —
  // shared by loadFromDb (library reload), loadFromRfq (RFQ→Deal booking
  // prefill) and loadFromDeal (reopening a booked deal), all of which
  // receive the same {name: value} constats blob.
  function _restoreConstats(saved) {
    for (const [k, v] of Object.entries(saved || {})) {
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
      barrier_monitoring: globalParams.barrierMonitoring,
      constats: _buildConstats(),
      // The CONSTAT calendar carries absolute dates; the engine needs year
      // fractions from the product's t=0, which is its value date — not the
      // day we happen to click "Pricer". Left unset, a deal priced today and
      // the same deal replayed after booking (api/deals.py anchors on
      // deal.value_date) resolve the same calendar differently.
      anchor: globalParams.value_date || null,
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
        dividendCurveEnabled: !!u.dividendCurveEnabled,
        dividendDecay: u.dividendDecay,
        dividendCurve: _buildDividendCurve(u),
      })),
      corrMatrix: corrMatrix.value.map(row => [...row]),
      r: globalParams.r, T: globalParams.T, N: globalParams.N, seed: globalParams.seed,
      model: globalParams.model, antithetic: globalParams.antithetic,
      rateModel: globalParams.rateModel, sigma_r: globalParams.sigma_r, a_r: globalParams.a_r,
      barrierMonitoring: globalParams.barrierMonitoring,
      trade_date: globalParams.trade_date, strike_date: globalParams.strike_date,
      value_date: globalParams.value_date,
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

  // ── Underlying comparator — backtest the script against a candidate pool
  // (managed locally in ComparatorTab.vue, independent from the underlyings
  // actually used for pricing) individually, then (if the product needs
  // more than one underlying) combined — see backend BacktestCompareRequest
  // docstring for the two-stage funnel. basket_size is NOT a user choice:
  // it's the number of underlyings the product currently has configured in
  // Marché & Paramètres (a worst-of-2 product searches for the best pair,
  // not an arbitrary basket size). ─────────────────────────────────────
  const comparator = ref(null)
  const comparatorError = ref('')
  const comparatorLoading = ref(false)

  async function runBacktestCompare(candidates, params = {}) {
    comparatorLoading.value = true; comparatorError.value = ''
    try {
      const res = await apiFetch('/api/backtest/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          script: script.value,
          candidates,
          r: globalParams.r / 100,
          T: globalParams.T,
          model: globalParams.model,
          user_params: _buildUserParams(),
          constats: _buildConstats(),
          basket_size: params.basket_size || 1,
          shortlist_n: params.shortlist_n || 8,
          start_date: params.start_date || '2010-01-01',
          end_date: params.end_date || null,
          freq: params.freq || 21,
          invest_pct: params.invest_pct || 100,
          rf_rate: params.rf_rate || 2.0,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Erreur ${res.status}`)
      }
      comparator.value = await res.json()
    } catch (e) {
      comparatorError.value = e.message
    } finally {
      comparatorLoading.value = false
    }
  }

  // Replace the current underlyings/correlation with a candidate basket
  // picked from the comparator, then refresh σ/q for the new tickers.
  async function adoptBasket(tickers, names, corrMat) {
    underlyings.value = tickers.map((tk, i) => ({
      ..._defaultUnderlying(i + 1),
      ticker: tk, name: names[i] || tk,
    }))
    // loadYfAll() also recalculates the correlation matrix itself (1y
    // window) as a side effect of refreshing σ/q — it would silently
    // overwrite the realized, full-history correlation from the backtest
    // that made this the winning basket. Re-apply it after, so what gets
    // priced matches exactly what "prix indicatif" already showed.
    corrMatrix.value = corrMat.map(row => [...row])
    await loadYfAll()
    corrMatrix.value = corrMat.map(row => [...row])
  }

  // ── Assistant de scripting IA ──────────────────────────────────────
  // `force` : re-sonde Ollama. La liste des modèles installés change dès qu'on
  // fait un `ollama pull`, et rien ne le signale à une page déjà ouverte.
  async function loadScriptProviders(force = false) {
    if (scriptProviders.value && !force) return scriptProviders.value
    try {
      const res = await fetch('/api/script/providers')
      if (res.ok) scriptProviders.value = await res.json()
    } catch { /* le sélecteur retombera sur Ollama */ }
    return scriptProviders.value
  }

  // Le prompt exact qui partirait, sans rien dépenser. Les exemples envoyés
  // dépendent de la description : les voir, c'est pouvoir ajuster sa demande
  // autrement qu'à tâtons.
  async function previewScriptPrompt(description) {
    try {
      const res = await fetch('/api/script/prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: description || 'produit structuré',
          underlyings: _buildUls(),
          corr_matrix: _buildCorr(),
          T: globalParams.T,
        }),
      })
      return res.ok ? await res.json() : null
    } catch { return null }
  }

  // `refine` repart de `currentScript` : « non, la barrière doit être observée
  // en continu » doit affiner, pas tout réécrire. Le script de départ est passé
  // explicitement — c'est celui que l'assistant vient de proposer, pas celui de
  // l'éditeur, qui n'a pas encore été adopté.
  async function generateScript({ description, provider, model, refine = false,
                                  currentScript = '' }) {
    scriptGenLoading.value = true
    scriptGenError.value = null
    try {
      const res = await fetch('/api/script/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description,
          provider,
          model: model || null,
          underlyings: _buildUls(),
          corr_matrix: _buildCorr(),
          r: globalParams.r / 100,
          T: globalParams.T,
          user_params: _buildUserParams(),
          current_script: refine ? currentScript : '',
          refine,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        scriptGenError.value = data.detail || 'Erreur serveur'
        scriptGen.value = null
      } else {
        scriptGen.value = data
      }
    } catch (e) {
      scriptGenError.value = e.message
      scriptGen.value = null
    } finally { scriptGenLoading.value = false }
  }

  // Adoption explicite : le script ne descend dans l'éditeur que sur action de
  // l'utilisateur. Un script qui atterrirait tout seul, c'est un produit faux
  // qui part en cotation.
  function adoptGeneratedScript() {
    if (!scriptGen.value?.script) return
    script.value = scriptGen.value.script
    parseScript()
  }

  // ── Mark to Future (nested Monte Carlo) ────────────────────────────
  async function runMtf(params = {}) {
    if (!result.value) { error.value = 'Lancez d\'abord un pricing (▶ Pricer).'; return }
    const n_outer = params.n_outer || 200
    const n_inner = params.n_inner || 500
    const n_dates = params.n_dates || 5
    const body = {
      ..._baseBody(),
      main_price: result.value.price * 100,
      n_outer, n_inner, n_dates,
      seed: params.seed || globalParams.seed,
    }
    loading.value = true; error.value = null
    // Rough cost calibration: ~4.7s for the 200×500×5 default on a GBM/local-vol model.
    _startProgress((n_outer * n_inner * n_dates / 500000) * 4700)
    try {
      const res = await fetch('/api/mtf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) { const err = await res.json(); error.value = err.detail || 'Erreur serveur' }
      else {
        mtf.value = await res.json()
        // Le corps EXACT qui a produit cet éventail. Le drill-down le rejoue tel
        // quel au lieu de reconstruire un _baseBody() : sinon une modification du
        // script entre le lancement et le clic expliquerait un autre produit que
        // celui affiché, sans que rien ne le signale.
        mtfBody.value = body
        mtfDrill.value = null
        rightTab.value = 'mtf'
      }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // Explication détaillée de scénarios choisis à une date de l'éventail.
  // `ids` sont des indices dans mtf.results[i].pvs — le client sait déjà quel
  // scénario porte quel quantile, inutile de refaire tourner tout l'éventail.
  async function runMtfDrilldown({ t, ids, labels = [] }) {
    if (!mtf.value || !mtfBody.value) {
      mtfDrillError.value = 'Lancez d\'abord un Mark to Future.'
      return
    }
    mtfDrillLoading.value = true
    mtfDrillError.value = null
    try {
      const res = await fetch('/api/mtf/drilldown', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...mtfBody.value, t, scenario_ids: ids, labels }),
      })
      if (!res.ok) {
        const err = await res.json()
        mtfDrillError.value = err.detail || 'Erreur serveur'
        mtfDrill.value = null
      } else {
        mtfDrill.value = await res.json()
      }
    } catch (e) {
      mtfDrillError.value = e.message
      mtfDrill.value = null
    } finally { mtfDrillLoading.value = false }
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
    // Cells now reprice in parallel across up to 4 worker processes (see
    // core/payscript/scenarios.py) instead of one sequential loop. Measured
    // live (45 cells, N=2000): ~4.2s sequential -> ~2.3-2.4s parallel, a real
    // but sub-linear ~1.8x speedup (process-pool spawn is per-request on
    // Windows `spawn`, so it doesn't scale 4x) — EFFECTIVE_SPEEDUP and
    // POOL_SPAWN_OVERHEAD_MS below are fit to that measurement, not the
    // naive worker count.
    const EFFECTIVE_SPEEDUP = 2
    const POOL_SPAWN_OVERHEAD_MS = 500
    const sequentialMs = cells * (N || 2000) / (45 * 2000) * 3000
    _startProgress(POOL_SPAWN_OVERHEAD_MS + sequentialMs / EFFECTIVE_SPEEDUP)
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

  // ── Stored spot lookup (Parquet price store — separate from hist_vol
  // above, which only calibrates σ/q on the fly and persists nothing) ──
  async function fetchStoredSpot(key, date) {
    const res = await fetch(`/api/amc/prices/spot?key=${encodeURIComponent(key)}&date=${encodeURIComponent(date)}`)
    if (!res.ok) return null
    return res.json()
  }

  async function refreshStoredSpot(key, ticker) {
    const res = await fetch('/api/amc/prices/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, ticker }),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur Yahoo Finance') }
    return res.json()
  }

  // ── Underlyings management ────────────────────────────────────────
  // ── Reset / Load from DB ──────────────────────────────────────────
  function _defaultUnderlying(n) {
    return {
      name: `Sous-jacent ${n}`, ticker: '', ccy: 'EUR',
      sigma: 20, q: 2.0, sigma_fx: 0, rho_sfx: 0, ccyh: 0,
      dividendCurveEnabled: false, dividendDecay: 10.0,
      v0: 4.0, kappa: 2.0, theta: 4.0, xi: 35, rho_h: -70, rho_rS: 40,
      alpha: 20, beta: 50, rho: -30, nu: 40,
      skew: -10, curvature: 5, showQuanto: false,
    }
  }

  function _clearResults() {
    result.value = null; profile.value = null; paths.value = null
    proba.value = null; backtest.value = null; mtf.value = null
    solver.value = null; grid.value = null; scenarios.value = null
    kid.value = null
    comparator.value = null
    currentIndicativeId.value = null
    currentRfqId.value = null
    openedDeal.value = null
    // An unconsumed prefill must die with the session it belonged to: it is
    // applied by whichever DealTab instance mounts NEXT, which — the Deal tab
    // being v-if'd on a persistent leftTab — can be one created much later,
    // for a completely unrelated pricing. loadFromRfq sets it AFTER calling
    // this, so its own handoff survives.
    pendingDealPrefill.value = null
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
      sigma_r: 1.5, a_r: 0.3, barrierMonitoring: 'weekly',
      value_date: new Date().toISOString().split('T')[0],
    })
    yieldCurve.enabled = false
    _clearResults()
    parseScript()
  }

  // Reopen a booked deal's exact frozen state — script, market params, full
  // underlyings/corr, PARAM overrides — so Script/Marché & Paramètres/Deal/
  // Events all agree, instead of showing whatever was last being edited here.
  async function loadFromDeal(deal) {
    const market = deal.market_snapshot || {}
    currentScriptId.value   = deal.script_id || null
    currentScriptName.value = deal.reference
    script.value = deal.script_snapshot

    if (market.underlyings?.length) {
      // Merge over full defaults: old / API-booked deals have a partial
      // snapshot ({name, ticker, ccy, sigma, q}) — missing model fields
      // would flow as undefined → NaN → null → 422 at pricing time.
      // Explicit nulls in the snapshot are dropped for the same reason.
      underlyings.value = market.underlyings.map((u, i) => ({
        ..._defaultUnderlying(i + 1),
        ...Object.fromEntries(Object.entries(u).filter(([, v]) => v != null)),
      }))
      corrMatrix.value = market.corrMatrix?.length ? market.corrMatrix : [[1.0]]
      activeUnderlyingIdx.value = 0
    }

    Object.assign(globalParams, {
      r: market.r ?? globalParams.r,
      T: deal.T,
      model: market.model ?? globalParams.model,
      antithetic: market.antithetic ?? globalParams.antithetic,
      deal_ccy: market.deal_ccy ?? deal.devise,
      rateModel: market.rateModel ?? globalParams.rateModel,
      sigma_r: market.sigma_r ?? globalParams.sigma_r,
      a_r: market.a_r ?? globalParams.a_r,
      trade_date: deal.trade_date,
      strike_date: deal.strike_date,
      value_date: deal.value_date,
    })

    if (market.yieldCurve?.length) {
      yieldCurve.enabled = true
      yieldCurve.pillars = market.yieldCurve
    }

    _clearResults()
    await parseScript()

    // Restore the CONSTAT calendars frozen at booking (after parseScript, so
    // the names exist in constatOverrides to be filled). Without this, an
    // Expert-mode deal reopened here kept the calendar's default EMPTY dates
    // and the first ▶ Pricer died on "CONSTAT X: champ 'start_date'
    // manquant" — while the Events tab, which reads the deal's own stored
    // observation dates, displayed a perfectly complete schedule. Every deal
    // booked out of a "to trade" RFQ hits this: that kind REQUIRES a CONSTAT
    // script (api/rfq.py:create_rfq).
    _restoreConstats(market.constats || {})

    // Restore the PARAM overrides frozen at booking. Without this, the
    // params card under the script shows the SCRIPT's seed defaults, not
    // the deal's actual negotiated terms (a degressive PARAM() barrier
    // would collapse back to one row). user_params are stored-units
    // fractions — convert back to display units via each param's is_pct.
    const up = market.user_params || {}
    for (const [name, v] of Object.entries(up)) {
      if (!(name in paramOverrides)) continue
      if (Array.isArray(v)) {
        paramOverrides[name] = v.map(x => fromStoredUnits(name, x))
      } else {
        paramOverrides[name] = fromStoredUnits(name, v)
      }
    }

    // The deal's commercial terms live in DealTab's own form, not here — so
    // reopening a booked deal has to hand them over the same way the RFQ path
    // does. Without this the Deal tab showed an empty booking form
    // (contrepartie "— Choisir —", fair value and prix traité at 0) on a deal
    // that carries all of it, and re-booking from there produced a duplicate.
    openedDeal.value = { id: deal.id, reference: deal.reference }
    pendingDealPrefill.value = {
      sens: deal.sens,
      contrepartie: deal.contrepartie || '',
      product_type: deal.product_type || '',
      fixing_policy: deal.fixing_policy || 'AUTO_YAHOO',
      fair_value: deal.fair_value,
      price_traded: deal.price_traded,
      trade_date: deal.trade_date,
      strike_date: deal.strike_date,
      value_date: deal.value_date,
      payment_date: deal.payment_date,
      nominal: deal.nominal,
    }
  }

  // Pre-fill the Pricer from an RFQ's retained ("retenue") quote — script,
  // underlyings, params from the RFQ itself; contrepartie/price_traded from
  // the selected quote, handed off to DealTab.vue via pendingDealPrefill
  // since those live in the component's own form, not this store. Mirrors
  // loadFromDeal, but the RFQ's params blob is the lighter shape RfqView.vue
  // builds at creation (single r/T/N/model, no Heston/SABR/curve fields) —
  // same defensive merge-over-defaults as loadFromDeal handles that fine.
  async function loadFromRfq(rfqObj) {
    const p = rfqObj.params || {}
    currentScriptId.value   = rfqObj.script_id || null
    currentScriptName.value = rfqObj.reference
    script.value = rfqObj.script_snapshot

    if (p.underlyings?.length) {
      // Unlike Deal.market_snapshot (percentage numbers, e.g. 20 for 20% —
      // straight from underlyings.value, see _snapshotInputs), RfqView.vue
      // persists sigma/q as raw fractions (advanced.sigma / 100, matching
      // the backend request-body convention) — convert back to the store's
      // percentage-number convention or _buildUls() silently divides by 100
      // a second time (0.2 -> 0.002, a near-zero vol that breaks pricing).
      underlyings.value = p.underlyings.map((u, i) => {
        const { sigma, q, dividend_curve, dividend_decay, ...rest } = u
        const inferredDecay = dividend_curve?.length > 1 && dividend_curve[0]?.[1] > 0
          ? (1 - dividend_curve[1][1] / dividend_curve[0][1]) * 100
          : 0
        return {
          ..._defaultUnderlying(i + 1),
          ...Object.fromEntries(Object.entries(rest).filter(([, v]) => v != null)),
          ...(sigma != null ? { sigma: sigma * 100 } : {}),
          ...(q != null ? { q: q * 100 } : {}),
          dividendCurveEnabled: !!dividend_curve?.length,
          dividendDecay: dividend_decay != null ? dividend_decay * 100 : inferredDecay,
        }
      })
      corrMatrix.value = p.corr_matrix?.length ? p.corr_matrix : [[1.0]]
      activeUnderlyingIdx.value = 0
    }

    Object.assign(globalParams, {
      r: (p.r ?? globalParams.r / 100) * 100,
      T: p.T ?? globalParams.T,
      model: p.model || globalParams.model,
      deal_ccy: p.currency || globalParams.deal_ccy,
      strike_date: p.strike_date || globalParams.strike_date,
      value_date: p.value_date || globalParams.value_date,
      // The whole point of landing in the Pricer is to re-run the price and
      // check it against the RFQ's — which only means something if the
      // simulation context matches too, not just the product. rfq.js's
      // computeModelPrice sends script/underlyings/r/T/N/model/user_params/
      // constats and nothing else, so its price was produced with the
      // PricingRequest defaults (core/schemas.py) for everything below.
      // Inherit those instead of whatever this session was last set to, or a
      // Pricer left on N=100k with the yield curve enabled reprices a
      // legitimately different number and the comparison proves nothing.
      N: p.N ?? 20000,
      seed: 42,
      antithetic: true,
      rateModel: 'deterministic',
      barrierMonitoring: 'weekly',
    })
    yieldCurve.enabled = false

    _clearResults()
    currentRfqId.value = rfqObj.id
    await parseScript()

    const up = p.user_params || {}
    for (const [name, v] of Object.entries(up)) {
      if (!(name in paramOverrides)) continue
      paramOverrides[name] = Array.isArray(v)
        ? v.map(x => fromStoredUnits(name, x))
        : fromStoredUnits(name, v)
    }

    _restoreConstats(p.constats || {})

    const selected = (rfqObj.quotes || []).find(q => q.id === rfqObj.selected_quote_id)
    pendingDealPrefill.value = {
      // quote.counterparty is the ELIGIBLE counterparty the server resolved
      // from the provider (explicit link or identical name — see api/rfq.py
      // _counterparty_by_provider), not the provider label. The two catalogs
      // are distinct: writing the label straight in booked deals against a
      // counterparty absent from the eligibility list, invisible in the
      // <select> that shows it. Unresolved (null) is passed through as such —
      // DealTab leaves the field empty and says why rather than guessing.
      ...(selected ? {
        contrepartie: selected.counterparty ?? '',
        rfq_provider_label: selected.provider,
        price_traded: selected.price ?? 0,
      } : {}),
      ...(p.notional != null ? { nominal: p.notional } : {}),
      product_type: rfqObj.template_type || '',
      // Deal.sens is written from the COUNTERPARTY's side ("Vente (banque
      // vend)"), the RFQ's from ours — so an RFQ where WE buy books as a deal
      // whose sens is 'vente'. Inverted here rather than unifying the two
      // conventions, which would silently re-read every deal already booked.
      sens: rfqObj.sens === 'vente' ? 'achat' : 'vente',
      // Seed fair_value from the RFQ's own model price (already in percentage
      // points, like DealTab's field). _clearResults() just wiped
      // store.result, so DealTab's fair-value watch has nothing to fire on
      // and would otherwise leave 0 — booking a deal whose P&L baseline says
      // the product is worthless. Re-pricing overwrites it with a fresh
      // number; until then fair_value_at tells DealTab how old this one is.
      ...(rfqObj.model_price != null
        ? { fair_value: rfqObj.model_price, fair_value_at: rfqObj.model_price_at }
        : {}),
    }
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

    if (data.constats_json) _restoreConstats(JSON.parse(data.constats_json))

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
        barrierMonitoring: globalParams.barrierMonitoring,
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
      dividendCurveEnabled: false, dividendDecay: 10.0,
      v0: 4.0, kappa: 2.0, theta: 4.0, xi: 35, rho_h: -70, rho_rS: 40,
      alpha: 20, beta: 50, rho: -30, nu: 40,
      skew: -10, curvature: 5, showQuanto: false,
    })
    const m = corrMatrix.value
    m.forEach(row => row.push(0))
    m.push(new Array(n+1).fill(0))
    m[n][n] = 1
    activeUnderlyingIdx.value = n
  }

  function removeUnderlying(i) {
    if (underlyings.value.length <= 1) return
    underlyings.value.splice(i, 1)
    corrMatrix.value.splice(i, 1)
    corrMatrix.value.forEach(row => row.splice(i, 1))
    activeUnderlyingIdx.value = Math.min(activeUnderlyingIdx.value, underlyings.value.length - 1)
  }

  return {
    leftTab, rightTab,
    script, scriptParams, parseError, paramOverrides, scriptConstats, constatOverrides, scriptHasStop,
    underlyings, corrMatrix, activeUnderlyingIdx,
    globalParams, yieldCurve, greekSel, selectedGreeks,
    result, profile, paths, proba, backtest, mtf, solver, grid, scenarios, kid,
    mtfDrill, mtfDrillLoading, mtfDrillError, runMtfDrilldown,
    scriptGen, scriptGenLoading, scriptGenError, scriptProviders,
    loadScriptProviders, generateScript, adoptGeneratedScript, previewScriptPrompt,
    comparator, comparatorError, comparatorLoading, runBacktestCompare, adoptBasket,
    loading, error, progress, yfStatus,
    currentScriptId, currentScriptName,
    currentIndicativeId, productTitle, ensureIndicative,
    currentRfqId, pendingDealPrefill, openedDeal,
    parseScript, runPricing, runGreeks,
    runProfile, runPaths, runProba, runBacktest, runMtf,
    runSolver, runGrid, paramIsPct, fromStoredUnits, runScenarios, fetchSchedulePreview,
    buildUserParams: _buildUserParams,
    buildConstats: _buildConstats,
    buildDividendCurve: _buildDividendCurve,
    loadYfOne, loadYfAll, fetchStoredSpot, refreshStoredSpot,
    addUnderlying, removeUnderlying,
    resetToDefaults, loadFromDb, loadFromDeal, loadFromRfq, saveScript, updateScript,
    pricingBody: () => ({ ..._baseBody(), N: globalParams.N, antithetic: globalParams.antithetic, ..._rateParams() }),
  }
})
