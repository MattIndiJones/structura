// Solveur, grille et scénarios.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.

export function installSimulationTools(s) {
  const {
    _baseBody, _prepareCalculation, _startProgress, _stopProgress, error, grid, loading,
    rightTab, scenarios, scriptParams, solver,
  } = s

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
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    loading.value = true; error.value = null
    _startProgress((N || 8000) / 8000 * ((max_iter || 40) / 40) * 1500)
    try {
      if (lo == null || hi == null || lo === '' || hi === '' || !(Number(lo) < Number(hi))) throw new Error('Renseignez deux bornes de recherche croissantes.')
      const data = await s._queuedAnalysis('/api/solve', {
          ..._baseBody({ omit: [param_name] }),
          param_name,
          target_price: target_price_pct / 100,
          lo: toStoredUnits(param_name, lo),
          hi: toStoredUnits(param_name, hi),
          N: N || 8000, tol: tol || 1e-4, max_iter: max_iter || 40,
      })
      if (data) { solver.value = data; rightTab.value = 'simulation' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  async function runGrid({ param_x, x_min, x_max, x_steps, param_y, y_min, y_max, y_steps, N }) {
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    loading.value = true; error.value = null
    _startProgress((N || 4000) * (x_steps || 9) * (y_steps || 9) / (4000 * 81) * 3000)
    try {
      if ([x_min, x_max, y_min, y_max].some(v => v == null || v === '') || !(Number(x_min) < Number(x_max)) || !(Number(y_min) < Number(y_max))) throw new Error('Renseignez les bornes croissantes de chaque axe.')
      const data = await s._queuedAnalysis('/api/grid', {
          ..._baseBody({ omit: [param_x, param_y] }),
          param_x, x_min: toStoredUnits(param_x, x_min), x_max: toStoredUnits(param_x, x_max),
          x_steps: x_steps || 9,
          param_y, y_min: toStoredUnits(param_y, y_min), y_max: toStoredUnits(param_y, y_max),
          y_steps: y_steps || 9,
          N: N || 4000,
      })
      if (data) { grid.value = data; rightTab.value = 'simulation' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Scenarios: spot x vol stress grid ──────────────────────────────
  // spot_shocks_pct/vol_shocks_pct are plain percentages from the UI (e.g. -10
  // for -10% spot, 5 for +5pp vol) — divided by 100 here to match the stored
  // fraction units run_mc expects (spot_mult/vol_add).
  async function runScenarios({ spot_shocks_pct, vol_shocks_pct, N }) {
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
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
      const data = await s._queuedAnalysis('/api/scenarios', {
          ..._baseBody(),
          spot_shocks: spot_shocks_pct.map(v => v / 100),
          vol_shocks: vol_shocks_pct.map(v => v / 100),
          N: N || 2000,
      })
      if (data) { scenarios.value = data; rightTab.value = 'scenarios' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  Object.assign(s, { paramIsPct, toStoredUnits, fromStoredUnits, runSolver, runGrid, runScenarios })
}
