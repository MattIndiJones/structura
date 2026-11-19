// Store du Pricer. Découpé le 18/11/2026 : chaque domaine vit dans
// src/stores/pricing/<domaine>.js et s'installe sur un contexte partagé `s`,
// dans l'ordre ci-dessous. L'objet renvoyé — l'interface que voient les
// composants — est inchangé.
import { CALCULATION_LIMITS } from '../utils/calculationBudget.js'
import { defineStore } from 'pinia'
import { installScriptState } from './pricing/scriptState.js'
import { installMarketInputs } from './pricing/marketInputs.js'
import { installProductContext } from './pricing/productContext.js'
import { installRequestState } from './pricing/requestState.js'
import { installParsePrepare } from './pricing/parsePrepare.js'
import { installDates } from './pricing/dates.js'
import { installRuns } from './pricing/runs.js'
import { installMtf } from './pricing/mtf.js'
import { installSimulationTools } from './pricing/simulationTools.js'
import { installMarketData } from './pricing/marketData.js'
import { installSession } from './pricing/session.js'
import { installLoaders } from './pricing/loaders.js'
import { installPersistence } from './pricing/persistence.js'

export const usePricingStore = defineStore('pricing', () => {
  const s = {}
  installScriptState(s)
  installMarketInputs(s)
  installProductContext(s)
  installRequestState(s)
  installParsePrepare(s)
  installDates(s)
  installRuns(s)
  installMtf(s)
  installSimulationTools(s)
  installMarketData(s)
  installSession(s)
  installLoaders(s)
  installPersistence(s)

  const {
    _baseBody, _buildConstats, _buildCorr, _buildDividendCurve, _buildUls, _buildUserParams,
    _fundingPayload, _inLifeBody, _pricingBody, activeUnderlyingIdx, addUnderlying,
    adoptBasket, adoptGeneratedScript, adoptedGeneratedScriptText, backtest,
    beginProductTermsEdit, comparator, comparatorError, comparatorLoading,
    confirmParameterConversion, constatOverrides, contractTermsLocked, corrMatrix,
    currentIndicativeId, currentProduct, currentRfqExecution, currentRfqId, currentScriptId,
    currentScriptName, editingProductTerms, ensureIndicative, ensureScriptValidated, error,
    fromStoredUnits, fundingCurve, globalParams, greekSel, greeksEstimate, grid,
    hasUnsavedSession, hestonCalibrationPending, impliedFunding, initialFixingName,
    isInLife, isPreStrike, kid, leftTab, loadDividendProfile, loadFromDb, loadFromDeal,
    loadFromPreset, loadFromProduct, loadFromProductModel, loadFromRfq, loadStrikeCloses,
    loadTranscribeEngines, loadVariant, loadYfAll, loadYfOne, loading, marketDataAsOf,
    marketDataEffectiveDate, marketDataLoading, maturityDate, maturityDateEditable,
    maturityError, mtf, mtfActiveLeg, mtfComparison, mtfDrill, mtfDrillError,
    mtfDrillLoading, mtfIsStale, mtfLoading, onUnderlyingSelection, onValuationDateChange,
    openedDeal, paramIsPct, paramOverrides, parameterConversions, parseError, parseScript,
    paths, pendingDealPrefill, prepareBookingFork, prepareTranscribe, pricingEstimate,
    pricingJob, cancelPricing, proba, productLoadNotice, productTitle, profile, progress, relacherVariante,
    releaseSession, removeUnderlying, resetToDefaults, result, resultIsStale, rightTab,
    runBacktest, runBacktestCompare, runGreeks, runGrid, runImpliedFunding,
    runInLifePricing, runMtf, runMtfDrilldown, runPaths, runPricing, runProba, runProfile,
    runScenarios, runSolver, saveConfiguration, saveScript, saveVariant, scenarios, script,
    scriptAssistantPayload, scriptConstats, scriptDirty, scriptGen, scriptGenLoading,
    scriptGenerationProvenance, scriptHasMaturityEvent, scriptHasStop, scriptParams,
    selectMtfLeg, selectedGreeks, sessionRouteKey, setMaturityDate, solver, startDate,
    syncTenorFromMaturity, transcribeAudio, transcribeEngines, underlyings, updateScript,
    usesDatedPricing, validateScript, validationReport, variantComparisonInputs,
    variantDirty, variantInfo, yfStatus, yieldCurve,
  } = s

  return {
    leftTab, rightTab,
    script, scriptParams, parseError, paramOverrides, scriptConstats, constatOverrides,
    scriptHasStop, scriptHasMaturityEvent,
    scriptDirty, validationReport, validateScript, ensureScriptValidated,
    underlyings, corrMatrix, activeUnderlyingIdx,
    globalParams, maturityDate, maturityDateEditable, yieldCurve, greekSel, selectedGreeks,
    pricingEstimate, greeksEstimate, hestonCalibrationPending, calculationLimits: CALCULATION_LIMITS,
    result, resultIsStale, profile, paths, proba, backtest, mtf, solver, grid, scenarios, kid,
    mtfDrill, mtfDrillLoading, mtfDrillError, runMtfDrilldown,
    mtfComparison, mtfActiveLeg, mtfIsStale, mtfLoading, selectMtfLeg,
    scriptGen, scriptGenLoading,
    scriptGenerationProvenance,
    scriptAssistantPayload, adoptGeneratedScript,
    transcribeEngines, loadTranscribeEngines, transcribeAudio, prepareTranscribe,
    comparator, comparatorError, comparatorLoading, runBacktestCompare, adoptBasket,
    loading, error, progress, pricingJob, cancelPricing, yfStatus, marketDataLoading, marketDataAsOf, marketDataEffectiveDate,
    currentScriptId, currentScriptName,
    // Le corps que l'écran envoie pour SON prix. Exposé pour que la
    // comparaison de variantes s'y adosse plutôt que d'en refaire un —
    // deux voies de construction finiraient par classer des produits
    // que l'écran ne price pas.
    inLifeBody: _inLifeBody,
    currentIndicativeId, currentProduct, variantComparisonInputs, productTitle, ensureIndicative,
    currentRfqId, currentRfqExecution, pendingDealPrefill, openedDeal, contractTermsLocked,
    editingProductTerms, beginProductTermsEdit, productLoadNotice, parameterConversions, confirmParameterConversion,
    initialFixingName, startDate, saveConfiguration,
    draftProductBody: () => _baseBody({ allowMissing: true }),
    parseScript, runPricing, runGreeks,
    runProfile, runPaths, runProba, runBacktest, runMtf,
    runSolver, runGrid, paramIsPct, fromStoredUnits, runScenarios,
    runInLifePricing, isInLife, isPreStrike, usesDatedPricing, loadDividendProfile,
    fundingCurve, runImpliedFunding, impliedFunding,
    buildUserParams: _buildUserParams,
    buildConstats: _buildConstats,
    buildDividendCurve: _buildDividendCurve,
    scriptProvenance: () => scriptGenerationProvenance.value
      ? { ...scriptGenerationProvenance.value,
          modified_after_adoption: script.value !== adoptedGeneratedScriptText.value }
      : null,
    loadYfOne, loadYfAll, onValuationDateChange, onUnderlyingSelection, loadStrikeCloses,
    setMaturityDate, syncTenorFromMaturity, maturityError,
    addUnderlying, removeUnderlying,
    resetToDefaults, releaseSession, sessionRouteKey, loadFromDb, loadVariant, saveVariant, variantInfo,
    relacherVariante,
    variantDirty,
    loadFromDeal, loadFromRfq, loadFromProduct, prepareBookingFork, saveScript, updateScript,
    loadFromProductModel, loadFromPreset, hasUnsavedSession,
    pricingBody: _pricingBody,
    optimizerMarketInputs: () => ({
      model: globalParams.model, rate_model: globalParams.rateModel,
      currency: globalParams.deal_ccy,
      as_of: globalParams.valuation_date || marketDataAsOf.value || globalParams.strike_date || new Date().toLocaleDateString('en-CA'),
      r: globalParams.r / 100, underlyings: _buildUls(), corr_matrix: _buildCorr(),
      yield_curve: yieldCurve.enabled ? yieldCurve.pillars.map(p => [p.T,p.rate/100]) : [],
      ..._fundingPayload(),
    }),
  }
})
