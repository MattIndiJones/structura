// États des résultats et construction des corps de requête.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { apiFetch } from '../../utils/api.js'
import { calendarPolicy } from '../../utils/payscriptEconomics.js'
import { computed, ref, watch } from 'vue'
import { courbeDividende } from '../../composables/useDividendCurve.js'
import { explicitHestonCalibration } from '../../utils/smileCalibration.js'
import { hasCalendarDefaultState, registerCalendarDefaults, suggestedCalendars, syncCalendarDefault } from '../../composables/useCalendarDefaults.js'
import { marketProvenanceFields } from '../../utils/marketProvenance.js'
import { _canonical, _restoreTenor, _tenorStr } from './helpers.js'

export function installRequestState(s) {
  const {
    _activeBookedContract, _contractUnderlyings, _fundingPayload, constatOverrides,
    contractTermsLocked, corrMatrix, currentProduct, currentRfqId, editingProductTerms,
    globalParams, initialFixingName, paramOverrides, parameterConversions, script,
    scriptConstats, scriptParams, startDate, underlyings, yieldCurve,
  } = s

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
  const scriptGenerationProvenance = ref(null)
  const adoptedGeneratedScriptText = ref('')
  // Dictée : état du moteur local (installé ? poids téléchargés ?). Sondé une
  // seule fois, le paquet ne s'installe pas en cours de session.
  const transcribeEngines = ref(null)
  // Corps de requête ayant produit `mtf`, rejoué à l'identique par le drill-down.
  const mtfBody   = ref(null)
  const mtfComparison = ref(null)
  const mtfActiveLeg = ref(null)
  const mtfLoading = ref(false)
  const mtfContext = ref(null)
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
  s._pricingRevision = 0
  s._parseRevision = 0

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

  watch(startDate, value => { if (initialFixingName.value) globalParams.strike_date = value }, { flush: 'sync' })

  // ── Helpers ───────────────────────────────────────────────────────
  function _buildUserParams({ omit = [], allowMissing = false } = {}) {
    const up = {}
    for (const p of scriptParams.value) {
      if (omit.includes(p.name)) continue
      if (parameterConversions[p.name]) throw new Error(`Confirmez la conversion de ${p.name} en scalaire dans Economics.`)
      const v = p.name in paramOverrides ? paramOverrides[p.name] : p.display_default
      if (allowMissing && (v == null || (typeof v === 'string' && !v.trim()))) {
        up[p.name] = null
        continue
      }
      if (Array.isArray(v)) {
        if (!v.length) throw new Error(`Le paramètre ${p.name} doit contenir au moins une valeur.`)
        up[p.name] = v.map((x, index) => {
          if (x == null || (typeof x === 'string' && x.trim() === '')) {
            if (allowMissing) return null
            throw new Error(`Le paramètre ${p.name}, ligne ${index + 1}, est requis.`)
          }
          const number = Number(x)
          if (typeof x === 'boolean' || !Number.isFinite(number)) {
            throw new Error(`Le paramètre ${p.name}, ligne ${index + 1}, doit être numérique.`)
          }
          return p.is_pct ? number / 100 : number
        })
      } else {
        if (v == null || (typeof v === 'string' && v.trim() === '')) {
          throw new Error(`Le paramètre ${p.name} est requis.`)
        }
        const number = Number(v)
        if (typeof v === 'boolean' || !Number.isFinite(number)) {
          throw new Error(`Le paramètre ${p.name} doit être numérique.`)
        }
        up[p.name] = p.is_pct ? number / 100 : number
      }
    }
    return up
  }

  function _hestonEvidence(u, horizon = globalParams.T, rate = globalParams.r) {
    if (yieldCurve.enabled || _rateParams().sigma_r || u.dividendCurveEnabled || u.ccyh || u.fx_mode
        || u.sigma_fx * u.rho_sfx) return null
    return explicitHestonCalibration(u, horizon, rate)?.calibration_evidence ?? null
  }

  function _buildUls(rows = underlyings.value, model = globalParams.model) {
    return rows.map(u => {
      const evidence = model === 'heston' ? _hestonEvidence(u) : u.calibration_evidence
      return {
      name: u.name, ticker: u.ticker, ccy: u.ccy, spot0: u.spot0 || null,
      sigma: u.sigma / 100,
      q: u.q / 100,
      dividend_curve: _buildDividendCurve(u).map(p => [p.T, p.rate / 100]),
      dividend_decay: u.dividendCurveEnabled
        ? Math.max(0, Math.min(100, Number(u.dividendDecay) || 0)) / 100
        : 0,
      sigma_fx: u.sigma_fx / 100,
      rho_sfx: u.rho_sfx / 100,
      ccyh: u.ccyh / 10000,
      ...(u.fx_mode ? {
        fx_mode: u.fx_mode, r_ccy: Number(u.r_ccy) / 100,
        ...(u.ccyCurveEnabled && u.ccyCurve?.length
          ? { ccy_curve: u.ccyCurve.map(p => [Number(p.T), Number(p.rate) / 100]) } : {}),
      } : {}),
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
      asset_class: u.asset_class || 'unknown',
      smile_parameter_mode: model === 'heston' && !evidence ? 'manual' : u.smile_parameter_mode || 'automatic',
      ...(evidence ? {calibration_evidence: JSON.parse(JSON.stringify(evidence))} : {}),
      vol_surface: u.vol_surface ? JSON.parse(JSON.stringify(u.vol_surface)) : null,
      ...marketProvenanceFields(u),
      }
    })
  }

  // La dérivation vit dans useDividendCurve : l'écran d'appel d'offres en a
  // besoin avec SON horizon, et deux implémentations d'une convention de
  // bucket finiraient par décaler la courbe d'un an sans rien signaler.
  const _buildDividendCurve = (u) => u.dividendCurveEnabled && u._savedDividendCurve
    && u.q === u._savedDividendBase?.q && u.dividendDecay === u._savedDividendBase?.decay
    ? u._savedDividendCurve.map(p => ({ ...p })) : courbeDividende(u, globalParams.T)

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
    return _constatsFrom(constatOverrides, scriptConstats.value)
  }

  function _applyCalendarDefaults() {
    if (contractTermsLocked.value) return
    const proposed = suggestedCalendars(underlyings.value, globalParams.deal_ccy)
    for (const calendar of scriptConstats.value) {
      const value = constatOverrides[calendar.name]
      if (value && typeof value === 'object' && hasCalendarDefaultState(value)) for (const purpose of ['observation', 'settlement'])
        syncCalendarDefault(value, proposed, purpose)
    }
  }

  /**
   * Un jeu de CONSTAT, de la forme STOCKÉE vers la forme que le serveur attend.
   *
   * Les deux diffèrent : `frequency` est un objet {value, unit} à l'écran et
   * une chaîne « 1M » dans la requête. Envoyer la forme stockée telle quelle
   * faisait lever au serveur une AttributeError non rattrapée — un 500 en texte
   * brut, que le front ne savait même pas lire.
   *
   * Factorisé pour que les termes d'ORIGINE d'un avenant passent par la MÊME
   * transformation que ceux de l'écran. Une seconde conversion, côté serveur,
   * aurait redonné deux formes qui divergent.
   */
  function _constatsFrom(overrides, declares = null) {
    const out = {}
    // Sans déclaration de script, on lit la forme depuis la valeur elle-même :
    // une chaîne est une date unique, un objet un échéancier.
    const liste = declares || Object.keys(overrides || {}).map(name => ({
      name, kind: typeof overrides[name] === 'string' ? 'single' : 'schedule',
    }))
    for (const c of liste) {
      const v = (overrides || {})[c.name]
      if (v == null) continue
      if (typeof v === 'string') {
        out[c.name] = v
      } else if (c.kind === 'single') {
        // Date unique portant une fenêtre de constatation.
        out[c.name] = {
          ...calendarPolicy(v),
          date: v.date,
          window_length: _tenorStr(v.window_length),
          window_frequency: _tenorStr(v.window_frequency),
          convention: v.convention || 'none',
          settlement_lag: v.settlement_lag || 0,
        }
      } else {
        out[c.name] = {
          ...calendarPolicy(v),
          ...(initialFixingName.value ? { first_observation_date: v.first_observation_date, period_start_date: v.period_start_date || startDate.value } : { start_date: v.start_date }),
          end_date: v.end_date, roll_date: v.roll_date || v.first_observation_date,
          frequency: _tenorStr(v.frequency), stub: v.stub,
          window_length: _tenorStr(v.window_length),
          window_frequency: _tenorStr(v.window_frequency),
          sub_frequency: c.kind === 'nested_schedule' ? _tenorStr(v.sub_frequency) : null,
          // Le serveur les attend depuis le chantier des dates ; ils ne
          // partaient pas d'ici, si bien qu'une convention saisie dans le
          // Pricer n'avait aucun effet sur le calendrier réellement calculé.
          convention: v.convention || 'none',
          settlement_lag: v.settlement_lag || 0,
        }
      }
    }
    return out
  }

  // Mirrors _buildConstats()'s output shape back into constatOverrides —
  // shared by loadFromDb (library reload), loadFromRfq (RFQ→Deal booking
  // prefill) and loadFromDeal (reopening a booked deal), all of which
  // receive the same {name: value} constats blob.
  function _restoreConstats(saved, defaults = false) {
    for (const [k, v] of Object.entries(saved || {})) {
      if (!(k in constatOverrides)) continue
      if (typeof v === 'string') {
        constatOverrides[k] = v
      } else if (v && typeof v === 'object') {
        const ov = constatOverrides[k]
        // Legacy and generated deals store a plain single CONSTAT as a
        // structured {date, convention, settlement_lag} object, while the
        // compact editor historically kept it as a string. Restore the date
        // instead of silently leaving the field empty.
        if (typeof ov === 'string') {
          constatOverrides[k] = { ...v }
          registerCalendarDefaults(constatOverrides[k], defaults)
          continue
        }
        if (ov && typeof ov === 'object') {
          for (const field of ['observation_calendars', 'observation_join', 'settlement_calendars', 'settlement_join'])
            if (!Object.hasOwn(v, field)) delete ov[field]
          registerCalendarDefaults(ov, false)
          Object.assign(ov, JSON.parse(JSON.stringify(calendarPolicy(v))))
          // Une date unique portant une fenêtre est stockée comme objet : sa
          // date vit dans `date`, pas dans start_date.
          if (v.date !== undefined) ov.date = v.date || ''
          _restoreTenor(ov, v, 'window_length', { value: 10, unit: 'D' })
          _restoreTenor(ov, v, 'window_frequency', { value: 1, unit: 'D' })
          ov.first_observation_date = v.first_observation_date || ''
          ov.period_start_date = v.period_start_date || ''
          ov.start_date = v.start_date || ''
          ov.end_date   = v.end_date   || ''
          ov.roll_date  = v.roll_date  || ''
          ov.stub       = v.stub       || 'short_last'
          // Sans ça, rouvrir un deal booké ou recharger un script depuis la
          // bibliothèque perdait sa convention et son décalage de règlement :
          // le calendrier se recalculait sans eux, en silence.
          ov.convention     = v.convention     || 'none'
          ov.settlement_lag = v.settlement_lag || 0
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

  /**
   * Le corps commun à toutes les analytiques.
   *
   * Il passe par `_avecTermesDOrigine` comme le prix : sans ça, l'onglet
   * Probabilités rejouait le passé sous la barrière de la VARIANTE et comptait
   * des rappels qui n'ont jamais eu lieu. Le prix affichait une chose, la
   * distribution en décrivait une autre — et rien ne le signalait.
   */
  function _contractCalendar(frozen) {
    if (frozen?.calendar_status && (frozen.calendar_status !== 'FROZEN' || !frozen.frozen_schedule) && scriptConstats.value.length) {
      throw new Error('Calendrier contractuel figé indisponible ou incohérent : requalifiez le dossier avant repricing.')
    }
    return frozen?.frozen_schedule || (contractTermsLocked.value ? currentProduct.value?.terms?.resolved_events : null) || null
  }

  function _baseBody(parameterOptions = {}) {
    const frozen = _activeBookedContract()
    return s._avecTermesDOrigine({
      script: frozen?.script ?? script.value,
      underlyings: _contractUnderlyings(frozen),
      corr_matrix: _buildCorr(),
      r: globalParams.r / 100,
      T: frozen?.T ?? globalParams.T,
      seed: globalParams.seed,
      model: globalParams.model,
      antithetic: globalParams.antithetic,
      ..._rateParams(),
      user_params: frozen?.user_params ?? _buildUserParams(parameterOptions),
      yield_curve: yieldCurve.enabled
        ? yieldCurve.pillars.map(p => [p.T, p.rate / 100])
        : [],
      ..._fundingPayload(),
      barrier_monitoring: globalParams.barrierMonitoring,
      steps_per_year: globalParams.stepsPerYear,
      constats: frozen?.constats ?? _buildConstats(),
      // Les trois dates et la devise, exactement comme pour la valorisation en
      // cours de vie. Elles ne partaient pas d'ici : le serveur recevait un
      // décalage de règlement sans calendrier de devise pour le compter et
      // refusait le calcul — c'est ce qui cassait les Greeks dès qu'un CONSTAT
      // portait un règlement.
      strike_date: frozen?.strike_date ?? globalParams.strike_date ?? null,
      value_date: frozen?.value_date ?? globalParams.value_date ?? null,
      payment_date: frozen ? frozen.payment_date : (globalParams.payment_date || null),
      settlement_ccy: frozen?.settlement_ccy ?? globalParams.deal_ccy ?? null,
      // Ce qui fait basculer une analytique sur la vie restante. Absentes,
      // elle décrit le produit à l'émission — comportement historique.
      valuation_date: globalParams.valuation_date || null,
      maturity_date: frozen?.maturity_date ?? s._maturityDate(),
      frozen_schedule: _contractCalendar(frozen),
      // Le calendrier CONSTAT porte des dates absolues ; le moteur veut des
      // fractions d'année depuis l'origine de son axe, qui est la date de
      // STRIKE — là où le niveau initial se constate. Repli sur la value date
      // pour les produits qui n'en déclarent pas.
      anchor: frozen?.strike_date ?? frozen?.value_date
        ?? globalParams.strike_date ?? globalParams.value_date ?? null,
    })
  }

  // All pricing and Monte Carlo analyses share the active short-rate settings.
  // Derives the two backend params from the single rateModel selector so
  // switching back to "Déterministe" always sends 0 regardless of leftover
  // field values, and "ABM" always sends a_r=0 (no mean reversion).
  function _rateParams() {
    if (globalParams.rateModel === 'deterministic') return { sigma_r: 0, a_r: 0 }
    if (globalParams.rateModel === 'abm') return { sigma_r: globalParams.sigma_r / 100, a_r: 0 }
    return { sigma_r: globalParams.sigma_r / 100, a_r: globalParams.a_r }   // hull_white
  }

  function _requestKey(body) {
    // La seed décrit le tirage de ce run, pas le produit. La changer ne rend
    // donc pas économiquement caduc un prix déjà calculé.
    const { compute_greeks, selected_greeks, seed, ...priced } = body
    return JSON.stringify(_canonical(priced))
  }

  function _pricingBody() {
    if (s.usesDatedPricing()) return s._inLifeBody()
    return {
      ..._baseBody(), N: globalParams.N,
      antithetic: globalParams.antithetic, ..._rateParams(),
    }
  }

  const PRODUCT_TERM_FIELDS = new Set([
    'script', 'user_params', 'constats', 'T', 'strike_date', 'value_date',
    'maturity_date', 'payment_date', 'anchor', 'settlement_ccy', 'frozen_schedule',
  ])

  async function _authoritativeProductRequest(request) {
    if (editingProductTerms.value) throw new Error('Conservez la nouvelle version des termes avant de calculer ou de transmettre ce produit.')
    const product = currentProduct.value
    if (!product) return request
    const context = Object.fromEntries(
      Object.entries(request).filter(([key]) => !PRODUCT_TERM_FIELDS.has(key)))
    context.underlyings = (request.underlyings || []).map(underlying => {
      const { name, ticker, ccy, ...market } = underlying
      return market
    })
    const rfqId = currentRfqId.value
    const endpoint = rfqId ? `/api/rfq/${rfqId}/pricing-input` : `/api/products/${product.product_id}/pricing-input`
    const res = await apiFetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expected_terms_version: product.terms_version,
        context,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const detail = typeof data?.detail === 'string'
        ? data.detail : data?.detail?.message
      throw new Error(detail || 'Les termes du Product n’ont pas pu être chargés.')
    }
    return rfqId ? data.pricing_input : data
  }

  const resultIsStale = computed(() => {
    if (!result.value?._requestKey) return false
    try { return result.value._requestKey !== _requestKey(_pricingBody()) }
    catch { return true }
  })

  Object.assign(s, { result, profile, paths, proba, backtest, mtf, scriptGen, scriptGenLoading, scriptGenerationProvenance, adoptedGeneratedScriptText, transcribeEngines, mtfBody, mtfComparison, mtfActiveLeg, mtfLoading, mtfContext, mtfDrill, mtfDrillLoading, mtfDrillError, solver, grid, scenarios, kid, loading, error, progress, _progressTimer, _startProgress, _stopProgress, _buildUserParams, _hestonEvidence, _buildUls, _buildDividendCurve, _buildCorr, _buildConstats, _applyCalendarDefaults, _constatsFrom, _restoreConstats, _contractCalendar, _baseBody, _rateParams, _requestKey, _pricingBody, PRODUCT_TERM_FIELDS, _authoritativeProductRequest, resultIsStale })
}
