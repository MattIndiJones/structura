// Remise à zéro et suivi de la session.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { DEFAULT_SCRIPT, _declares, _defaultUnderlying, _localTodayIso } from './helpers.js'

export function installSession(s) {
  const {
    _clearMtf, activeUnderlyingIdx, adoptedGeneratedScriptText, backtest,
    bookedContractTerms, calendarKinds, calendarShapes, comparator, constatOverrides,
    contractTermsLocked, corrMatrix, currentIndicativeId, currentProduct,
    currentRfqExecution, currentRfqId, currentScriptId, currentScriptName,
    editingProductTerms, fundingCurve, globalParams, grid, kid, marketDataAsOf,
    marketDataEffectiveDate, marketDataLoading, maturityError, openedDeal, paramOverrides,
    parameterConversions, parameterShapes, parseError, parseScript, paths,
    pendingDealPrefill, proba, productLoadNotice, profile, relacherVariante, result,
    rightTab, scenarios, script, scriptAtDates, scriptConstats, scriptGenerationProvenance,
    scriptHasMaturityEvent, scriptHasStop, scriptParams, sessionRouteKey, solver,
    underlyings, validationReport, variantComparisonInputs, yfStatus, yieldCurve,
  } = s

  function _clearResults() {
    // Rend également toute réponse encore en vol inapplicable au nouveau
    // produit chargé dans le store.
    s._pricingRevision += 1
    result.value = null; profile.value = null; paths.value = null
    proba.value = null; backtest.value = null; _clearMtf()
    solver.value = null; grid.value = null; scenarios.value = null
    kid.value = null
    comparator.value = null
    currentIndicativeId.value = null
    currentProduct.value = null
    variantComparisonInputs.value = null
    editingProductTerms.value = false
    productLoadNotice.value = ''
    currentRfqId.value = null
    currentRfqExecution.value = null
    openedDeal.value = null
    bookedContractTerms.value = null
    // An unconsumed prefill must die with the session it belonged to: it is
    // applied by whichever DealTab instance mounts NEXT, which — the Deal tab
    // being v-if'd on a persistent leftTab — can be one created much later,
    // for a completely unrelated pricing. loadFromRfq sets it AFTER calling
    // this, so its own handoff survives.
    pendingDealPrefill.value = null
    rightTab.value = 'empty'
  }

  function _resetInputState() {
    // A Yahoo response belonging to the product being left must never land on
    // the next product that reuses this global Pinia store.
    s._marketDataRevision += 1
    s.automaticMarketRequest = null
    s.lastAutomaticMarketKey = null
    relacherVariante()
    currentScriptId.value = null
    currentScriptName.value = ''
    scriptGenerationProvenance.value = null
    adoptedGeneratedScriptText.value = ''
    script.value = DEFAULT_SCRIPT
    // The next parse repopulates the declarations. Keeping the previous
    // product's declarations while their values are deleted below let
    // Economics render a calendar card (or a PARAM() table) with no value
    // behind it: a render error that broke the Pricer when « Nouveau Pricing »
    // or a product model replaced a session holding a CONSTAT() schedule.
    scriptParams.value = []
    scriptConstats.value = []
    scriptAtDates.value = []
    scriptHasStop.value = false
    scriptHasMaturityEvent.value = false
    parseError.value = null
    validationReport.value = null
    maturityError.value = ''
    underlyings.value = [_defaultUnderlying(1)]
    corrMatrix.value = [[1.0]]
    activeUnderlyingIdx.value = 0
    for (const key of Object.keys(paramOverrides)) delete paramOverrides[key]
    for (const table of [parameterConversions, parameterShapes, calendarShapes, calendarKinds]) {
      for (const key of Object.keys(table)) delete table[key]
    }
    for (const key of Object.keys(constatOverrides)) delete constatOverrides[key]
    const today = _localTodayIso()
    Object.assign(globalParams, {
      r: 3.0, T: null, N: 20000, seed: 42, model: 'constant',
      antithetic: true, deal_ccy: 'EUR', rateModel: 'deterministic',
      sigma_r: 1.5, a_r: 0.3, barrierMonitoring: 'weekly', stepsPerYear: 52,
      nominal: 1_000_000,
      trade_date: today, strike_date: '', value_date: '',
      maturity_date: '', payment_date: '', valuation_date: today,
    })
    yfStatus.value = ''
    marketDataAsOf.value = ''
    marketDataEffectiveDate.value = ''
    marketDataLoading.value = false
    Object.assign(yieldCurve, {
      enabled: false, ancree: false, ecart: 120, tau: 4.0,
      pillars: [
        { label: '3M', T: 0.25, rate: 3.2 }, { label: '6M', T: 0.5, rate: 3.4 },
        { label: '1Y', T: 1, rate: 3.6 }, { label: '2Y', T: 2, rate: 3.8 },
        { label: '3Y', T: 3, rate: 3.9 }, { label: '5Y', T: 5, rate: 4.0 },
        { label: '7Y', T: 7, rate: 4.1 }, { label: '10Y', T: 10, rate: 4.2 },
        { label: '15Y', T: 15, rate: 4.25 }, { label: '20Y', T: 20, rate: 4.3 },
        { label: '30Y', T: 30, rate: 4.35 },
      ],
    })
    Object.assign(fundingCurve, {
      enabled: false, mode: 'flat', level: 0,
      pillars: [0.25, 0.5, 1, 2, 3, 5, 7, 10].map(T => ({
        label: T < 1 ? `${Math.round(T * 12)}M` : `${T}Y`, T, spread: 0,
      })),
    })
  }

  function resetToDefaults() {
    sessionRouteKey.value = 'draft'
    _resetInputState()
    _clearResults()
    parseScript().then(_markSessionBaseline)
  }

  function releaseSession() {
    _resetInputState()
    _clearResults()
    sessionRouteKey.value = null
  }

  // ── Session: unsaved changes ──────────────────────────────────────
  // What the user would lose if the session were replaced: the product
  // (script, values, calendars, basket, typed dates) — not the market nor the
  // results, which are recomputed. The payment date is left out: Economics
  // proposes it on its own after every load.
  let _sessionBaseline = null

  function _sessionSnapshot() {
    return JSON.stringify({
      script: script.value,
      params: _declares(paramOverrides, scriptParams.value),
      constats: _declares(constatOverrides, scriptConstats.value),
      underlyings: underlyings.value.map(u => [u.name, u.ticker, u.ccy]),
      dates: [globalParams.strike_date, globalParams.value_date, globalParams.maturity_date],
      nominal: globalParams.nominal,
      ccy: globalParams.deal_ccy,
      variantComparisonInputs: variantComparisonInputs.value,
    })
  }

  function _markSessionBaseline() {
    _sessionBaseline = _sessionSnapshot()
  }

  /** True when replacing the session would lose a modified product. */
  function hasUnsavedSession() {
    if (_sessionBaseline === null || (contractTermsLocked.value && !variantComparisonInputs.value)) return false
    return _sessionSnapshot() !== _sessionBaseline
  }

  Object.assign(s, { _clearResults, _resetInputState, resetToDefaults, releaseSession, _sessionBaseline, _sessionSnapshot, _markSessionBaseline, hasUnsavedSession })
}
