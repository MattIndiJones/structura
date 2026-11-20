// Chargement depuis un modèle, un preset, un produit, un deal, une RFQ ou la base.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { CALCULATION_LIMITS } from '../../utils/calculationBudget.js'
import { PERCENT_MARKET_FIELDS, fractionToPercent, fractionToPercentExact } from '../../utils/underlyingDefaults.js'
import { apiFetch } from '../../utils/api.js'
import { buildModelCalendars } from '../../utils/productModels.js'
import { normaliseCorrelation } from '../../utils/rfqBasket.js'
import { readPricingConfiguration } from '../../utils/pricingConfiguration.js'
import { registerCalendarDefaults } from '../../composables/useCalendarDefaults.js'
import { _defaultUnderlying, _localTodayIso } from './helpers.js'

export function installLoaders(s) {
  const {
    _applyCalendarDefaults, _buildConstats, _buildUserParams, _clearResults,
    _installScriptValidation, _markSessionBaseline, _maturityDate, _resetInputState,
    _restoreConstats, _sessionSnapshot, activeUnderlyingIdx, adoptedGeneratedScriptText,
    bookedContractTerms, constatOverrides, contractTermsLocked, corrMatrix, currentProduct,
    currentRfqExecution, currentRfqId, currentScriptId, currentScriptName, error,
    fromStoredUnits, fundingCurve, globalParams, leftTab, marketDataAsOf,
    marketDataEffectiveDate, openedDeal, paramOverrides, parseScript, pendingDealPrefill,
    productLoadNotice, relacherVariante, script, scriptConstats, scriptGenerationProvenance,
    startDate, syncTenorFromMaturity, underlyings, variantInfo, yfStatus, yieldCurve,
  } = s

  /**
   * Opens a sheet of the « Modèles de produits » catalogue (M6–M9, 14/09/2026).
   *
   * With a tenor: the generic script, N underlyings at the Pricer's default
   * assumptions (zero correlation, tickers to pick), and calendars generated
   * from the Pricer's strike date (M8) to strike + tenor. The maturity follows
   * (M4), and T with it; Economics then proposes the payment at maturity + 3
   * business days.
   *
   * Without a tenor: the generic script and nothing else — no calendar and no
   * invented date, strike included. Pricing's own messages say what is missing.
   *
   * Once opened, the dates are independent: changing the strike date
   * afterwards does not move the calendar (M13).
   */
  async function loadFromProductModel(model, { underlyingCount = null, tenorCode = null } = {}) {
    _resetInputState()
    _clearResults()
    const min = Math.max(1, model.underlyings?.min || 1)
    const max = Math.max(min, Math.min(model.underlyings?.max || min, CALCULATION_LIMITS.maxUnderlyings))
    const count = Math.max(min, Math.min(max, Number(underlyingCount) || min))
    underlyings.value = Array.from({ length: count }, (_, i) => _defaultUnderlying(i + 1))
    corrMatrix.value = Array.from({ length: count }, (_, i) =>
      Array.from({ length: count }, (__, j) => (i === j ? 1.0 : 0.0)))
    activeUnderlyingIdx.value = 0
    script.value = model.script

    const plan = tenorCode
      ? buildModelCalendars(model, { strikeDate: _localTodayIso(), tenorCode })
      : null
    if (!plan) {
      globalParams.strike_date = ''
      globalParams.value_date = ''
    }

    await parseScript()
    for (const declared of scriptConstats.value) {
      const generated = plan?.constats?.[declared.name]
      if (!generated) continue
      const current = constatOverrides[declared.name]
      if (declared.kind === 'single') {
        if (current && typeof current === 'object') {
          current.date = generated.date
          if (generated.window_length) current.window_length = { ...generated.window_length }
          if (generated.window_frequency) current.window_frequency = { ...generated.window_frequency }
        } else {
          constatOverrides[declared.name] = generated.date
        }
      } else if (current && typeof current === 'object') {
        Object.assign(current, {
          start_date: generated.start_date, first_observation_date: generated.first_observation_date,
          period_start_date: generated.period_start_date, end_date: generated.end_date,
          roll_date: generated.roll_date, stub: generated.stub,
          convention: generated.convention, settlement_lag: generated.settlement_lag,
        })
        if (generated.frequency) current.frequency = { ...generated.frequency }
        if (generated.window_length) current.window_length = { ...generated.window_length }
        if (generated.window_frequency) current.window_frequency = { ...generated.window_frequency }
      }
    }
    if (plan) { globalParams.strike_date = startDate.value; syncTenorFromMaturity() }
    _markSessionBaseline()
  }

  /** Replace product terms with a reviewed example, keeping the desk's market. */
  async function loadFromPreset(plan) {
    if (contractTermsLocked.value) throw Error('Les termes de ce contrat sont figés. Ouvrez un nouveau pricing pour charger un exemple.')
    if (!plan?.validation?.data?.ok || plan.validation.script !== plan.model?.script)
      throw Error('Préparez et validez l’exemple avant de le charger.')
    if (plan.currency !== globalParams.deal_ccy)
      throw Error('La devise a changé. Préparez à nouveau l’exemple.')
    const { min = 1, max = 1 } = plan.model.underlyings || {}
    if (underlyings.value.length < min || underlyings.value.length > max)
      throw Error(`Cet exemple accepte ${min} à ${max} sous-jacents.`)
    const basket = underlyings.value, correlation = corrMatrix.value
    const active = activeUnderlyingIdx.value
    const globals = { ...globalParams }
    const curve = JSON.parse(JSON.stringify(yieldCurve))
    const funding = JSON.parse(JSON.stringify(fundingCurve))
    const market = [yfStatus.value, marketDataAsOf.value, marketDataEffectiveDate.value]
    _resetInputState()
    _clearResults()
    underlyings.value = basket; corrMatrix.value = correlation
    activeUnderlyingIdx.value = active
    Object.assign(globalParams, globals, {
      strike_date: plan.strikeDate, value_date: plan.strikeDate,
      maturity_date: plan.maturityDate, payment_date: plan.paymentDate,
      valuation_date: globalParams.valuation_date || _localTodayIso(), T: plan.T,
    })
    Object.assign(yieldCurve, curve); Object.assign(fundingCurve, funding)
    yfStatus.value = market[0]
    marketDataAsOf.value = market[1]
    marketDataEffectiveDate.value = market[2]
    script.value = plan.model.script
    await parseScript({ validation: plan.validation })
    Object.assign(paramOverrides, JSON.parse(JSON.stringify(plan.params)))
    _restoreConstats(plan.constats, true)
    for (const value of Object.values(constatOverrides)) if (value && typeof value === 'object') registerCalendarDefaults(value)
    _applyCalendarDefaults()
    error.value = null
    leftTab.value = 'economics'
    _markSessionBaseline()
  }

  function _productUnderlying(identity, market, index) {
    const out = { ..._defaultUnderlying(index + 1), ...identity }
    if(market?.market_data)out.market_data=JSON.parse(JSON.stringify(market.market_data))
    out.vol_surface=market?.vol_surface ? JSON.parse(JSON.stringify(market.vol_surface)) : null
    out.asset_class=market?.asset_class || 'unknown'
    out.smile_parameter_mode=market?.smile_parameter_mode || 'automatic'
    if(market?.calibration_evidence) out.calibration_evidence=JSON.parse(JSON.stringify(market.calibration_evidence))
    out._smileDefaults=false
    out.vol_level_source='saved'
    for (const field of PERCENT_MARKET_FIELDS) {
      if (market?.[field] != null) out[field] = fractionToPercentExact(market[field])
    }
    if (market?.ccyh != null) out.ccyh = Number(market.ccyh) * 10000
    if (market?.kappa != null) out.kappa = Number(market.kappa)
    const curve = market?.dividend_curve || []
    if (curve.length) {
      out.dividendCurveEnabled = true
      out.q = fractionToPercentExact(market.q ?? curve[0][1])
      out.dividendDecay = curve.length > 1 && Number(curve[0][1]) > 0
        ? Math.max(0, Math.min(100,
          (1 - Number(curve[1][1]) / Number(curve[0][1])) * 100))
        : fractionToPercent(market?.dividend_decay || 0)
      out._savedDividendCurve = curve.map(([T, rate]) => ({ T, rate: fractionToPercentExact(rate) }))
      out._savedDividendBase = { q: out.q, decay: out.dividendDecay }
    }
    return out
  }

  /** Ouvre le Product comme source contractuelle et remet, si elle existe,
   *  la dernière hypothèse de marché dans les champs du pricer. */
  async function loadFromProduct(product, calculationInput = null) {
    const response = await apiFetch('/api/parse', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script: product.terms.script }) })
    const validation = await response.json()
    if (!response.ok || !validation.ok || !Array.isArray(validation.params)) {
      throw new Error('Les termes du Product ne peuvent pas être validés. La session précédente est conservée.')
    }
    _resetInputState()
    _clearResults()
    const terms = product.terms
    const market = calculationInput || {}
    script.value = terms.script
    currentScriptName.value = product.reference || product.name

    const assumptions = market.underlyings || []
    underlyings.value = terms.underlyings.map((identity, index) =>
      _productUnderlying(identity, assumptions[index] || {}, index))
    corrMatrix.value = Array.isArray(market.corr_matrix)
      && market.corr_matrix.length === terms.underlyings.length
      ? market.corr_matrix.map(row => [...row])
      : terms.underlyings.map((_, i) => terms.underlyings.map((__, j) => i === j ? 1 : 0))
    activeUnderlyingIdx.value = 0

    Object.assign(globalParams, {
      r: market.r != null ? fractionToPercentExact(market.r) : globalParams.r,
      T: terms.T,
      N: market.N ?? globalParams.N,
      model: market.model || globalParams.model,
      antithetic: market.antithetic ?? globalParams.antithetic,
      deal_ccy: terms.settlement_ccy || globalParams.deal_ccy,
      nominal: product.intent?.nominal ?? globalParams.nominal,
      strike_date: terms.strike_date || '',
      value_date: terms.value_date || '',
      maturity_date: terms.maturity_date || '',
      payment_date: terms.payment_date || '',
      valuation_date: market.valuation_date || _localTodayIso(),
      barrierMonitoring: market.barrier_monitoring || 'weekly', stepsPerYear: market.steps_per_year ?? 52,
      rateModel: Number(market.sigma_r || 0) === 0
        ? 'deterministic' : (Number(market.a_r || 0) === 0 ? 'abm' : 'hull_white'),
      sigma_r: fractionToPercentExact(market.sigma_r || 0),
      a_r: Number(market.a_r || 0),
    })
    if (Array.isArray(market.yield_curve) && market.yield_curve.length) {
      yieldCurve.enabled = true
      yieldCurve.pillars = market.yield_curve.map(([T, rate]) => ({
        label: T < 1 ? `${Math.round(T * 12)}M` : `${T}Y`, T, rate: fractionToPercentExact(rate),
      }))
    }
    if (Array.isArray(market.funding_curve) && market.funding_curve.length) {
      fundingCurve.enabled = true
      fundingCurve.mode = 'pillars'
      fundingCurve.pillars = market.funding_curve.map(([T, spread]) => ({
        label: T < 1 ? `${Math.round(T * 12)}M` : `${T}Y`, T, spread: fractionToPercentExact(spread),
      }))
    } else if (market.funding_spread != null) {
      fundingCurve.enabled = Number(market.funding_spread) !== 0
      fundingCurve.mode = 'flat'
      fundingCurve.level = fractionToPercentExact(market.funding_spread)
    }

    s._parseRevision += 1
    _installScriptValidation(script.value, validation)
    for (const parameter of terms.parameters || []) {
      if (!(parameter.name in paramOverrides)) continue
      paramOverrides[parameter.name] = Array.isArray(parameter.value)
        ? parameter.value.map(value => value == null ? null : fromStoredUnits(parameter.name, value))
        : parameter.value == null ? null : fromStoredUnits(parameter.name, parameter.value)
    }
    _restoreConstats(terms.constats || {})
    currentProduct.value = product
    const intent = product.intent || {}
    const execution = product.execution || {}
    pendingDealPrefill.value = {
      sens: intent.side === 'SELL' ? 'achat' : 'vente',
      counterparty_id: intent.counterparty_id ?? null,
      contrepartie: intent.counterparty_name || '',
      product_type: intent.product_type || '',
      transaction_format: intent.transaction_format || '',
      instrument_family: intent.instrument_family || '',
      payoff_family: intent.payoff_family || '',
      payoff_description: intent.payoff_description || '',
      documentation_reference: intent.documentation_reference || '',
      client_id: product.commercial?.client_id ?? null,
      mandate_id: product.commercial?.mandate_id ?? null,
      opportunity_id: product.commercial?.opportunity_id ?? null,
      primary_affiliation_id: product.commercial?.primary_affiliation_id ?? null,
      commercial_context: null, commercial_reason: '',
      fair_value: execution.fair_value ?? 0,
      price_traded: execution.price_traded ?? 0,
      trade_date: execution.trade_date || globalParams.trade_date,
    }
    _markSessionBaseline()
  }

  function prepareBookingFork(product) {
    const origin = currentProduct.value?.product_id || openedDeal.value?.product_id
    if (!origin || product.origin_product_id !== origin || product.execution
        || product.rfqs?.length || product.indicatives?.length) {
      throw new Error('La nouvelle opération ne correspond pas au dossier source.')
    }
    _clearResults()
    currentProduct.value = product
    productLoadNotice.value = 'Nouvelle opération reliée au dossier d’origine. RFQ et indicatif détachés ; relancez le prix et confirmez le contexte commercial.'
    _markSessionBaseline()
  }

  // Reopen a booked deal's exact frozen state — script, market params, full
  // underlyings/corr, PARAM overrides — so Script/Marché & Paramètres/Deal/
  // Events all agree, instead of showing whatever was last being edited here.
  async function loadFromDeal(deal) {
    _resetInputState()
    _clearResults()
    const market = deal.market_snapshot || {}
    scriptGenerationProvenance.value = market.ai_script_provenance || null
    adoptedGeneratedScriptText.value = (
      scriptGenerationProvenance.value?.adopted_script_text || '')
    currentScriptId.value   = deal.script_id || null
    currentScriptName.value = deal.reference
    script.value = deal.script_snapshot

    const savedUnderlyings = market.underlyings?.length
      ? market.underlyings : (deal.underlyings?.length ? deal.underlyings : null)
    if (!savedUnderlyings) {
      throw new Error('Le deal ne contient aucun sous-jacent exploitable dans son snapshot.')
    }
    if (savedUnderlyings.length) {
      // Merge over full defaults: old / API-booked deals have a partial
      // snapshot ({name, ticker, ccy, sigma, q}) — missing model fields
      // would flow as undefined → NaN → null → 422 at pricing time.
      // Explicit nulls in the snapshot are dropped for the same reason.
      underlyings.value = savedUnderlyings.map((u, i) => ({
        ..._defaultUnderlying(i + 1),
        ...Object.fromEntries(Object.entries(u).filter(([, v]) => v != null)),
        _smileDefaults: false,
        vol_level_source: 'saved',
      }))
      corrMatrix.value = market.corrMatrix?.length ? market.corrMatrix : [[1.0]]
      activeUnderlyingIdx.value = 0
    }

    Object.assign(globalParams, {
      r: market.r ?? globalParams.r,
      T: deal.T,
      N: market.N ?? globalParams.N,
      seed: 42,
      model: market.model ?? globalParams.model,
      antithetic: market.antithetic ?? globalParams.antithetic,
      deal_ccy: market.deal_ccy ?? deal.devise,
      nominal: deal.nominal ?? globalParams.nominal,
      rateModel: market.rateModel ?? globalParams.rateModel,
      sigma_r: market.sigma_r ?? globalParams.sigma_r,
      a_r: market.a_r ?? globalParams.a_r,
      barrierMonitoring: market.barrierMonitoring ?? 'weekly', stepsPerYear: market.pricing_input?.steps_per_year ?? market.stepsPerYear ?? 52,
      trade_date: deal.trade_date,
      strike_date: deal.strike_date,
      value_date: deal.value_date,
      maturity_date: deal.maturity_date || '',
      payment_date: deal.payment_date || '',
      // La date de calcul est un choix de repricing, pas un terme contractuel.
      // Un deal rouvert part donc toujours de la date locale du jour ; strike,
      // value date et maturité restent, eux, ceux du contrat figé.
      valuation_date: _localTodayIso(),
    })

    if (market.yieldCurve?.length) {
      yieldCurve.enabled = true
      yieldCurve.pillars = market.yieldCurve
    }

    const savedFunding = market.funding
    const engineFundingCurve = market.funding_curve || []
    if (savedFunding?.enabled && savedFunding.mode === 'pillars') {
      fundingCurve.enabled = true
      fundingCurve.mode = 'pillars'
      fundingCurve.level = Number(savedFunding.level) || 0
      fundingCurve.pillars = (savedFunding.pillars || []).map(p => ({ ...p }))
    } else if (engineFundingCurve.length) {
      fundingCurve.enabled = true
      fundingCurve.mode = 'pillars'
      fundingCurve.level = Number(engineFundingCurve[0]?.[1] || 0) * 100
      fundingCurve.pillars = engineFundingCurve.map(([T, spread]) => ({
        label: T < 1 ? `${Math.round(T * 12)}M` : `${T}Y`, T, spread: fractionToPercent(spread),
      }))
    } else {
      // Un deal sans funding est un cas valide. Le zéro reste visible et
      // éditable ; il ne reprend jamais le spread du deal ouvert avant lui.
      fundingCurve.enabled = true
      fundingCurve.mode = 'flat'
      fundingCurve.level = savedFunding?.enabled
        ? (Number(savedFunding.level) || 0)
        : Number(market.funding_spread || 0) * 100
    }

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

    // The deal's commercial terms live in DealTab's own form, while its
    // economics live in this shared store. Reopening hands the commercial
    // terms over the same way as the RFQ path. Without this Deal showed an empty booking form
    // (contrepartie "— Choisir —", fair value and prix traité at 0) on a deal
    // that carries all of it, and re-booking from there produced a duplicate.
    // Keep a private contractual projection as a second line of defence. The
    // UI is read-only, but this also prevents a future component from sending
    // a silently edited payoff under the booked deal's reference.
    bookedContractTerms.value = {
      script: deal.script_snapshot,
      underlyings: underlyings.value.map(u => ({
        name: u.name, ticker: u.ticker || '', ccy: u.ccy,
      })),
      user_params: JSON.parse(JSON.stringify(_buildUserParams())),
      constats: JSON.parse(JSON.stringify(_buildConstats())),
      T: Number(deal.T ?? globalParams.T),
      strike_date: deal.strike_date || null,
      value_date: deal.value_date || deal.strike_date || null,
      maturity_date: deal.maturity_date || _maturityDate() || null,
      payment_date: deal.payment_date || null,
      settlement_ccy: market.deal_ccy ?? deal.devise ?? globalParams.deal_ccy,
      frozen_schedule: deal.frozen_schedule || null,
      calendar_status: deal.calendar_status,
    }
    const retainedSchedule = deal.schedule || deal.frozen_schedule?.schedule
    openedDeal.value = {
      id: deal.id, reference: deal.reference, contract_version: deal.contract_version,
      booked_steps_per_year: market.pricing_input?.steps_per_year ?? market.stepsPerYear ?? 52,
      product_id: deal.product_id, product_terms_version: deal.product_terms_version,
      counterparty_id: deal.counterparty_id, ccr_netting_set_id: deal.ccr_netting_set_id,
      uat_batch_id: deal.uat_batch_id, devise: deal.devise,
      ...(retainedSchedule ? { schedule: JSON.parse(JSON.stringify(retainedSchedule)) } : {}),
    }
    pendingDealPrefill.value = {
      sens: deal.sens,
      contrepartie: deal.contrepartie || '',
      counterparty_id: deal.counterparty_id || null,
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
    _markSessionBaseline()
  }

  // Pre-fill the Pricer from an RFQ's retained ("retenue") quote — script,
  // underlyings, params and economics from the RFQ itself; contrepartie and
  // price_traded from the selected quote are handed to DealTab.vue via
  // pendingDealPrefill because they remain local to that component. Mirrors
  // loadFromDeal, but the RFQ's params blob is the lighter shape RfqView.vue
  // builds at creation (single r/T/N/model, no Heston/SABR/curve fields) —
  // same defensive merge-over-defaults as loadFromDeal handles that fine.
  async function loadFromRfq(rfqObj) {
    _resetInputState()
    _clearResults()
    currentProduct.value = null
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
      underlyings.value = p.underlyings.map((u, i) => _productUnderlying(u, u, i))
      corrMatrix.value = normaliseCorrelation(p.corr_matrix, underlyings.value.length)
      activeUnderlyingIdx.value = 0
    }

    Object.assign(globalParams, {
      r: fractionToPercent(p.r ?? globalParams.r / 100),
      T: p.T ?? globalParams.T,
      model: p.model || globalParams.model,
      deal_ccy: p.currency || globalParams.deal_ccy,
      nominal: p.notional ?? globalParams.nominal,
      strike_date: p.strike_date || globalParams.strike_date,
      value_date: p.value_date || globalParams.value_date,
      maturity_date: p.maturity_date || globalParams.maturity_date,
      // La date de paiement AUSSI, et c'est la troisième du même term sheet :
      // l'oublier laissait le champ vide dans le masque de booking, où une
      // proposition en J+3 depuis la maturité venait le remplir. Cette date-là
      // n'est pas celle de l'AO — et `payment_date` fait partie des termes
      // contractuels gelés, donc le booking était refusé pour un écart que
      // personne n'avait saisi. Elle date l'échange final des flux : elle se
      // reprend, elle ne se recalcule pas.
      payment_date: p.payment_date || globalParams.payment_date,
      valuation_date: p.valuation_date || _localTodayIso(),
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
      antithetic: p.antithetic ?? true,
      rateModel: Number(p.sigma_r || 0) === 0
        ? 'deterministic' : (Number(p.a_r || 0) === 0 ? 'abm' : 'hull_white'),
      sigma_r: fractionToPercent(p.sigma_r || 0),
      a_r: Number(p.a_r || 0),
      barrierMonitoring: p.barrier_monitoring || 'weekly', stepsPerYear: p.steps_per_year ?? 52,
    })
    if (Array.isArray(p.yield_curve) && p.yield_curve.length) {
      yieldCurve.enabled = true
      yieldCurve.pillars = p.yield_curve.map(([T, rate]) => ({
        label: T < 1 ? `${Math.round(T * 12)}M` : `${T}Y`, T, rate: fractionToPercent(rate),
      }))
    }
    if (Array.isArray(p.funding_curve) && p.funding_curve.length) {
      fundingCurve.enabled = true
      fundingCurve.mode = 'pillars'
      fundingCurve.pillars = p.funding_curve.map(([T, spread]) => ({
        label: T < 1 ? `${Math.round(T * 12)}M` : `${T}Y`, T, spread: fractionToPercent(spread),
      }))
    } else if (p.funding_spread != null) {
      fundingCurve.enabled = Number(p.funding_spread) !== 0
      fundingCurve.mode = 'flat'
      fundingCurve.level = fractionToPercent(p.funding_spread)
    }
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
    currentRfqExecution.value = {
      requires_confirmation: selected?.origin === 'NETWORK',
      agreement: rfqObj.execution_agreements?.find(item => item.state !== 'CANCELLED') || null,
    }
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
        counterparty_id: selected.counterparty_id ?? null,
        rfq_provider_label: selected.provider,
        price_traded: selected.price ?? 0,
      } : {}),
      ...(p.notional != null ? { nominal: p.notional } : {}),
      product_type: rfqObj.template_type || '',
      // Le DealTab est déjà monté dans certains parcours et possède ses
      // propres watchers de proposition de règlement. Lui remettre les dates
      // dans le handoff final ferme la course entre ces propositions et le
      // chargement asynchrone de la RFQ : les dates du term sheet gagnent
      // toujours, même si un ancien produit était encore dans le store.
      ...(p.strike_date ? { strike_date: p.strike_date } : {}),
      ...(p.value_date ? { value_date: p.value_date } : {}),
      ...(p.maturity_date ? { maturity_date: p.maturity_date } : {}),
      ...(p.payment_date ? { payment_date: p.payment_date } : {}),
      client_id: rfqObj.client_id ?? null,
      mandate_id: rfqObj.mandate_id ?? null,
      opportunity_id: rfqObj.opportunity_id ?? null,
      primary_affiliation_id: rfqObj.primary_affiliation_id ?? null,
      commercial_context: rfqObj.commercial_context || null,
      transaction_format: rfqObj.transaction_format || '',
      instrument_family: rfqObj.instrument_family || '',
      payoff_family: rfqObj.payoff_family || '',
      payoff_description: rfqObj.payoff_description || '',
      documentation_reference: rfqObj.documentation_reference || '',
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
    _markSessionBaseline()
  }

  /**
   * Charge une VARIANTE : son contexte effectif, plus de quoi colorer.
   *
   * Le contexte arrive déjà résolu du serveur — parent + delta, et pour un
   * roll, dates déjà recalées. L'écran ne refait aucune de ces opérations :
   * les refaire ici ferait diverger ce qu'on affiche de ce qui price, et c'est
   * exactement l'écart qu'on passe son temps à fermer ailleurs.
   */
  async function loadVariant(vue) {
    const c = vue.contexte || {}
    await loadFromDb({
      id: vue.parent_id,
      name: vue.name,
      script_text: c.script_text || '',
      params_json: JSON.stringify(c.params || {}),
      constats_json: JSON.stringify(c.constats || {}),
      global_params_json: JSON.stringify(c.global || {}),
    })
    // Après loadFromDb, qui vient de la remettre à null.
    variantInfo.value = {
      id: vue.id, parent_id: vue.parent_id,
      title: vue.variant_title, mode: vue.variant_mode,
      ecarts: vue.ecarts || [],
      // Le delta ENREGISTRÉ, contre lequel se mesure ce que l'écran porte.
      delta: vue.delta || { set: {}, removed: [] },
      // Absent sur une note neuve : elle n'a pas de passé à rejouer.
      base: vue.base_pricing || null,
      // Le contexte de l'origine, contre lequel se calculent les écarts
      // au moment d'enregistrer.
      parent: vue.contexte_parent || null,
    }
  }

  async function loadFromDb(data, { scope = 'all' } = {}) {
    if (currentProduct.value || openedDeal.value || currentRfqId.value) throw new Error('Les termes de ce dossier sont figés ; ouvrez une nouvelle session pour appliquer une configuration.')
    if (!['terms', 'all'].includes(scope)) throw new Error('Portée de configuration inconnue.')
    const { params, calendars, global: saved } = readPricingConfiguration(data)
    const before = JSON.stringify([_sessionSnapshot(), underlyings.value, globalParams, yieldCurve, fundingCurve])
    const response = await apiFetch('/api/parse', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script: data.script_text }),
    })
    const validation = await response.json()
    if (!response.ok || !validation.ok || !Array.isArray(validation.params) || !Array.isArray(validation.constats || [])) {
      throw new Error('Configuration refusée : ' + (validation.errors || 'le script ne peut pas être validé.'))
    }
    for (const p of validation.params) {
      if (p.name in params && Array.isArray(params[p.name]) && p.kind !== 'array') throw new Error(`Configuration incompatible avec PARAM ${p.name}.`)
    }
    for (const c of validation.constats || []) {
      if (c.kind !== 'single' && typeof calendars[c.name] === 'string') throw new Error(`Calendrier ${c.name} incompatible avec la déclaration enregistrée.`)
    }
    if (saved.corr_matrix && !saved.underlyings && saved.corr_matrix.length !== underlyings.value.length) {
      throw new Error('Les corrélations enregistrées ne correspondent pas au panier conservé.')
    }
    if (before !== JSON.stringify([_sessionSnapshot(), underlyings.value, globalParams, yieldCurve, fundingCurve])
        || currentProduct.value || openedDeal.value || currentRfqId.value) {
      throw new Error('La session a changé pendant la préparation. Réappliquez la configuration.')
    }
    const preserved = {
      basket: JSON.parse(JSON.stringify(underlyings.value)), corr: JSON.parse(JSON.stringify(corrMatrix.value)),
      global: { ...globalParams }, yield: JSON.parse(JSON.stringify(yieldCurve)), funding: JSON.parse(JSON.stringify(fundingCurve)),
    }
    _resetInputState()
    const termKeys = new Set(['T', 'strike_date', 'value_date', 'maturity_date', 'payment_date', 'deal_ccy'])
    for (const [k, v] of Object.entries(preserved.global)) if (!termKeys.has(k)) globalParams[k] = v
    Object.assign(yieldCurve, preserved.yield); Object.assign(fundingCurve, preserved.funding)
    // Charger une ORIGINE efface toute variante affichée : sans ça, la barre
    // de déclinaison survivrait à la navigation et colorerait des champs par
    // rapport à un parent qui n'est plus à l'écran.
    relacherVariante()
    const configuration = saved.configuration
    currentScriptId.value   = configuration ? null : data.id
    currentScriptName.value = configuration ? '' : data.name
    script.value = data.script_text
    try {
      scriptGenerationProvenance.value = JSON.parse(data.ai_provenance_json || '{}')
      if (!Object.keys(scriptGenerationProvenance.value).length) {
        scriptGenerationProvenance.value = null
      }
    } catch { scriptGenerationProvenance.value = null }
    adoptedGeneratedScriptText.value = (
      scriptGenerationProvenance.value?.adopted_script_text || '')
    s._parseRevision += 1
    _installScriptValidation(data.script_text, validation)

    if (data.params_json) {
      for (const [k, v] of Object.entries(params)) {
        if (k in paramOverrides) paramOverrides[k] = v
      }
    }

    _restoreConstats(calendars)

    if (data.global_params_json) {
      for (const [k, v] of Object.entries(saved)) {
        if (k in globalParams) globalParams[k] = v
      }
      // Le panier et sa calibration. Fusionnés sur un sous-jacent par défaut
      // pour qu'un champ ajouté après la sauvegarde arrive avec sa valeur par
      // défaut plutôt qu'en undefined. Absents des scripts enregistrés avant
      // que ce soit sauvegardé : on garde alors ce qui est à l'écran.
      //
      // Une vol enregistrée est une hypothèse du pricing enregistré, comme
      // sur un deal ou un produit rouvert : marquée 'saved', elle n'est plus
      // remplacée par le défaut de sa classe d'actif quand le catalogue
      // arrive (marketInputs.js). Sans ce marquage, un script enregistré sans
      // origine de vol (créé par l'API, ou avant tout réglage) rouvrait à
      // 30 % au lieu de sa σ, quelques secondes après l'ouverture — un autre
      // prix, et le premier pricing lancé entre-temps écarté comme périmé.
      // Une origine explicite (saisie, marché) est gardée telle quelle.
      if (Array.isArray(saved.underlyings) && saved.underlyings.length) {
        underlyings.value = saved.underlyings.map((u, i) => ({
          ..._defaultUnderlying(i + 1), ...u, _smileDefaults: false,
          vol_level_source: u.vol_level_source && u.vol_level_source !== 'default' ? u.vol_level_source : 'saved',
        }))
      }
      if (Array.isArray(saved.corr_matrix) && saved.corr_matrix.length) {
        corrMatrix.value = saved.corr_matrix.map(row => [...row])
      }
      if (saved.funding) {
        fundingCurve.enabled = saved.funding.enabled ?? preserved.funding.enabled
        fundingCurve.mode = saved.funding.mode || preserved.funding.mode
        fundingCurve.level = saved.funding.level ?? preserved.funding.level
        if (Array.isArray(saved.funding.pillars) && saved.funding.pillars.length) {
          fundingCurve.pillars = saved.funding.pillars.map(x => ({ ...x }))
        }
      }
      if (saved.yield_curve_enabled != null) {
        yieldCurve.enabled = !!saved.yield_curve_enabled
        if (Array.isArray(saved.yield_curve_pillars) && saved.yield_curve_pillars.length) {
          yieldCurve.pillars = saved.yield_curve_pillars.map(x => ({ ...x }))
        }
      }
    }

    if (!saved.underlyings || scope === 'terms') {
      underlyings.value = preserved.basket; corrMatrix.value = preserved.corr
    }
    if (scope === 'terms') {
      for (const [k, v] of Object.entries(preserved.global)) if (!termKeys.has(k)) globalParams[k] = v
      Object.assign(yieldCurve, preserved.yield); Object.assign(fundingCurve, preserved.funding)
    }

    _clearResults()
    _markSessionBaseline()
  }

  Object.assign(s, { loadFromProductModel, loadFromPreset, _productUnderlying, loadFromProduct, prepareBookingFork, loadFromDeal, loadFromRfq, loadVariant, loadFromDb })
}
