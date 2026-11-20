// Mark-to-Future et son détail par date.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { calibrateUnderlying } from '../../utils/smileCalibration.js'
import { computed } from 'vue'
import { surfaceCalibrationKey } from '../../utils/volSurface.js'
import { apiErrorMessage } from '../../utils/api.js'

export function installMtf(s) {
  const {
    _authoritativeProductRequest, _baseBody, _buildUls, _hestonEvidence,
    _prepareScriptCalculation, _requestKey, currentProduct, editingProductTerms, error,
    globalParams, mtf, mtfActiveLeg, mtfBody, mtfComparison, mtfContext, mtfDrill,
    mtfDrillError, mtfDrillLoading, mtfLoading, openedDeal, result, resultIsStale, rightTab,
    underlyings,
  } = s
  let mtfRevision = 0
  let mtfDrillRevision = 0

  // Le Mark to Future, son détail et la comparaison de deux modèles passent
  // par la file de calcul (P1-4).
  async function _queuedMtf(route, body) {
    const res = await s._queuedCalculation(route, body)
    if (res.superseded) return null
    if (!res.ok) throw Error(apiErrorMessage(res.data, 'Calcul Mark to Future impossible.'))
    return res.data
  }

  // ── Mark to Future (nested Monte Carlo) ────────────────────────────
  const mtfIsStale = computed(() => mtfContext.value !== null &&
    (mtfContext.value !== _mtfContextKey() || resultIsStale.value || !result.value))

  function _mtfContextKey() {
    try {
      return JSON.stringify([_requestKey(_baseBody()), currentProduct.value, openedDeal.value?.id])
    } catch {
      return null
    }
  }

  function _clearMtf() {
    mtfRevision++
    mtfLoading.value = false
    mtfContext.value = null
    mtfComparison.value = null
    mtfActiveLeg.value = null
    _applyMtfResult(null, null)
  }

  function _applyMtfResult(fan, body) {
    mtfDrillRevision++
    mtfDrill.value = null
    mtfDrillLoading.value = false
    mtfDrillError.value = null
    mtf.value = fan
    mtfBody.value = fan ? { ...body, main_price: fan.main_price ?? body.main_price,
      mtm_dates: fan.mtm_dates, context_fingerprint: fan.context_fingerprint,
      ...(fan.lsv_qualification ? { lsv_qualification: fan.lsv_qualification } : {}) } : null
  }

  function selectMtfLeg(key) {
    const leg = mtfComparison.value?.[key]
    if (!leg?.result || mtfActiveLeg.value === key) return
    mtfActiveLeg.value = key
    _applyMtfResult(leg.result, leg.body)
  }

  async function _mtfModelBody(base, model, market, horizon) {
    if (model === 'gbm_atm_curve') return { ...base, model: 'constant', gbm_atm_curve: true }
    const indicative = model === 'heston_indicative'
    if (indicative) model = 'heston'
    if (!['constant', 'heston', 'sabr', 'localvol', 'lsv'].includes(model)) {
      throw Error('Modèle indisponible en MTF. Le levier LSV doit être qualifié avant activation.')
    }
    if (!['heston', 'sabr'].includes(model)) return { ...base, model }
    const inputs = structuredClone(market)
    await Promise.all(inputs.map(async u => {
      if (indicative) {
        if (!u.vol_surface?.atm_scenario) throw Error(`${u.name} · choisissez une courbe ATM par scénario.`)
        u.smile_parameter_mode = 'automatic'
        if (u.smile_calibration?.status !== 'unqualified' ||
            u.smile_calibration.key !== surfaceCalibrationKey(u, model, horizon, base.r * 100)) {
          await calibrateUnderlying(u, model, horizon, base.r * 100)
        }
        const fit = u.smile_calibration
        if (fit?.success !== true || !fit.calibration_evidence) {
          throw Error(`${u.name} · calibration Heston non convergée.`)
        }
        for (const [key, value] of Object.entries(fit.parameters)) u[key] = key === 'kappa' ? value : value * 100
        u.calibration_evidence = fit.calibration_evidence
        return
      }
      if (model === 'heston') {
        u.calibration_evidence = _hestonEvidence(u, horizon, base.r * 100)
        if (u.vol_surface && !u.calibration_evidence) u.smile_parameter_mode = 'manual'
        return
      }
      if (!u.vol_surface || u.smile_parameter_mode === 'manual') return
      await calibrateUnderlying(u, model, horizon, base.r * 100)
      if (u.smile_calibration?.status !== 'ready') {
        throw Error(`${u.name} · calibration ${model === 'sabr' ? 'SABR' : 'Heston'} non qualifiée.`)
      }
    }))
    const fields = ['v0', 'kappa', 'theta', 'xi', 'rho_h', 'alpha', 'beta', 'rho', 'nu',
      'smile_parameter_mode', 'calibration_evidence']
    const engineInputs = _buildUls(inputs, null)
    const calibrated = base.underlyings.map((u, i) => {
      const input = engineInputs[i]
      if (!input || input.name !== u.name || input.ticker !== u.ticker) {
        throw Error('Le panier du modèle ne correspond pas au produit valorisé.')
      }
      const parameters = Object.fromEntries(fields.filter(key => key in input).map(key => [key, input[key]]))
      return { ...u, ...parameters }
    })
    return { ...base, model, underlyings: calibrated, ...(indicative ? { indicative_heston: true } : {}) }
  }

  async function runMtf(params = {}) {
    if (!result.value) { error.value = "Lancez d'abord un pricing (▶ Pricer)."; return }
    if (resultIsStale.value) {
      error.value = 'Le prix de référence est périmé. Relancez le pricing avant le Mark to Future.'
      return
    }
    if (editingProductTerms.value) { error.value = 'Conservez les termes avant de lancer le MTF.'; return }
    const revision = ++mtfRevision
    mtfLoading.value = true
    error.value = null
    const reference = result.value
    let key = null
    const current = () => revision === mtfRevision && result.value === reference &&
      (key === null || key === _mtfContextKey())
    try {
      const preparing = _prepareScriptCalculation(message => { if (current()) error.value = message })
      if (preparing && !(await preparing)) return
      if (!current() || resultIsStale.value) return
      key = _mtfContextKey()
      const market = JSON.parse(JSON.stringify(underlyings.value))
      const referencePaths = reference._inputs?.N ?? globalParams.N
      const request = await _authoritativeProductRequest({ ..._baseBody(), N: referencePaths })
      if (!current()) return
      const base = { ...request, main_price: reference.price * 100, reference_paths: referencePaths,
        n_outer: params.n_outer || 200, n_inner: params.n_inner || 500, n_dates: params.n_dates || 5, seed: 42 }
      const horizon = reference.valuation_context?.T ?? reference.calculation_budget?.maturity_years ?? request.T
      const models = [params.model || request.model]
      if (params.modelB) models.push(params.modelB)
      if (models.length === 2 && models[0] === models[1]) throw Error('Sélectionnez deux modèles différents.')
      const prepared = await Promise.allSettled(models.map(model => _mtfModelBody(base, model, market, horizon)))
      if (!current()) return
      if (models.length === 1) {
        if (prepared[0].status === 'rejected') throw prepared[0].reason
        const body = prepared[0].value
        const fan = await _queuedMtf('/api/mtf', body)
        if (!fan || !current()) return
        mtfComparison.value = null
        mtfActiveLeg.value = null
        _applyMtfResult(fan, body)
      } else {
        const legs = Object.fromEntries(prepared.map((leg, i) => [['a', 'b'][i], leg.status === 'fulfilled'
          ? { model: models[i], body: leg.value } : { model: models[i], error: leg.reason.message }]))
        if (legs.a.body && legs.b.body) {
          const pair = await _queuedMtf('/api/mtf/compare', { a: legs.a.body, b: legs.b.body })
          if (!pair || !current()) return
          Object.assign(legs.a, pair.a, { model: models[0] })
          Object.assign(legs.b, pair.b, { model: models[1] })
        } else {
          const leg = legs.a.body ? legs.a : legs.b
          if (leg.body) {
            try { leg.result = await _queuedMtf('/api/mtf', leg.body) }
            catch (failure) { leg.error = failure.message }
          }
        }
        if (!current()) return
        mtfComparison.value = legs
        mtfActiveLeg.value = null
        const available = legs.a.result ? 'a' : legs.b.result ? 'b' : null
        if (available) selectMtfLeg(available)
        else _applyMtfResult(null, null)
      }
      mtfContext.value = key
      rightTab.value = 'mtf'
    } catch (e) { if (current()) error.value = e.message }
    finally { if (revision === mtfRevision) mtfLoading.value = false }
  }

  async function runMtfDrilldown({ t, ids, labels = [] }) {
    if (mtfIsStale.value || !mtf.value || !mtfBody.value) {
      mtfDrillError.value = 'Relancez le Mark to Future avant d’ouvrir le détail.'
      return
    }
    const revision = ++mtfDrillRevision
    const body = mtfBody.value
    mtfDrillLoading.value = true
    mtfDrillError.value = null
    mtfDrill.value = null
    try {
      const detail = await _queuedMtf('/api/mtf/drilldown', { ...body, t, scenario_ids: ids, labels })
      if (detail && revision === mtfDrillRevision && !mtfIsStale.value) mtfDrill.value = detail
    } catch (e) {
      if (revision === mtfDrillRevision && !mtfIsStale.value) mtfDrillError.value = e.message
    } finally { if (revision === mtfDrillRevision) mtfDrillLoading.value = false }
  }

  Object.assign(s, { mtfRevision, mtfDrillRevision, mtfIsStale, _mtfContextKey, _clearMtf, _applyMtfResult, selectMtfLeg, _mtfModelBody, runMtf, runMtfDrilldown })
}
