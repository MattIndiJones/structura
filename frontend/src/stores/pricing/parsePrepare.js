// Analyse du script et préparation des calculs.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { apiFetch } from '../../utils/api.js'
import { calibrateUnderlying } from '../../utils/smileCalibration.js'
import { computed } from 'vue'
import { surfaceCalibrationKey } from '../../utils/volSurface.js'
import { _declares } from './helpers.js'

export function installParsePrepare(s) {
  const {
    _applyDeclarationChanges, _buildDividendCurve, _hestonEvidence, _rateParams,
    _syncConstatOverrides, _syncParamOverrides, checkedScript, constatOverrides,
    contractTermsLocked, corrMatrix, currentProduct, currentScriptName, editingProductTerms,
    error, fundingCurve, globalParams, openedDeal, paramOverrides, parseError, script,
    scriptAtDates, scriptConstats, scriptHasMaturityEvent, scriptHasStop, scriptParams,
    underlyings, validatedScript, validationReport, yieldCurve,
  } = s
  let parseRequestFailed = false

  // ── Parse ─────────────────────────────────────────────────────────
  /**
   * Reads what the script declares and aligns Economics on it.
   *
   * Two uses, which differ only in how values are carried over:
   * - a LOAD (template, saved script, deal, RFQ, Product) calls `parseScript()`:
   *   the declarations become the reference, only new names are seeded, and
   *   the loader then restores its own values;
   * - an explicit VALIDATION passes `{ explicit: true }`: a declaration changed
   *   since the previous validation carries its new value over.
   *
   * Responses are sequenced: a stale one, or one arriving after a keystroke,
   * is ignored. Resolves to true when this text is now validated.
   */
  async function parseScript({ explicit = false, validation = null } = {}) {
    const revision = ++s._parseRevision
    const parsedScript = script.value
    if (!parsedScript.trim()) {
      scriptParams.value = []; scriptConstats.value = []; parseError.value = null
      parseRequestFailed = false
      scriptHasMaturityEvent.value = false
      scriptAtDates.value = []
      _syncParamOverrides(); _syncConstatOverrides()
      validatedScript.value = parsedScript
      checkedScript.value = parsedScript
      validationReport.value = explicit ? { replaced: [], keptRows: [] } : null
      return true
    }
    try {
      // A prepared example was validated before touching the current session.
      const res = validation?.script === parsedScript && validation.data?.ok
        ? { ok: true, json: async () => validation.data }
        : await apiFetch('/api/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script: parsedScript }),
      })
      const data = await res.json().catch(() => null)
      if (revision !== s._parseRevision || script.value !== parsedScript) return false
      checkedScript.value = parsedScript
      if (!res.ok) {
        const detail = typeof data?.detail === 'string' ? data.detail : data?.detail?.message
        const message = res.status === 401
          ? 'Session expirée ou absente : reconnectez-vous.'
          : res.status === 403
            ? 'Vous n’avez pas les droits nécessaires pour valider ce script.'
            : detail || `Le serveur a refusé la validation (HTTP ${res.status}).`
        throw new Error(message)
      }
      if (!data || typeof data.ok !== 'boolean') {
        throw new Error('Réponse inattendue du serveur de validation. Réessayez.')
      }
      parseRequestFailed = false
      if (!data.ok) {
        // A parse error means "I don't know what this script declares", not
        // "it declares nothing". The last valid reading is kept and NOT
        // synchronised: clearing the declarations then syncing used to wipe
        // every typed value.
        //
        // Nothing can be valued on stale declarations: a calculation
        // revalidates the script first and stops on this error.
        parseError.value = data.errors || 'Le serveur signale une erreur de syntaxe sans précision.'
        return false
      }
      _installScriptValidation(parsedScript, data, explicit)
      return true
    } catch (e) {
      if (revision === s._parseRevision && script.value === parsedScript) {
        checkedScript.value = parsedScript
        parseRequestFailed = true
        parseError.value = e.message
      }
      return false
    }
  }

  function _installScriptValidation(text, data, explicit = false) {
    const previousParams = scriptParams.value
    scriptParams.value = data.params; scriptConstats.value = data.constats || []
    scriptHasStop.value = data.has_stop ?? false
    scriptHasMaturityEvent.value = data.has_maturity_event ?? false
    scriptAtDates.value = Array.isArray(data.at_dates) ? data.at_dates : []
    parseError.value = null; parseRequestFailed = false
    validatedScript.value = text; checkedScript.value = text
    const report = explicit ? _applyDeclarationChanges(previousParams, data.params) : null
    _syncParamOverrides(); _syncConstatOverrides()
    validationReport.value = report
  }

  /** Ctrl+S and the « Valider » button: the explicit validation. */
  function validateScript() {
    return parseScript({ explicit: true })
  }

  /**
   * What a calculation must wait for before building its request.
   *
   * `null` when there is nothing to validate — and deliberately SYNCHRONOUS: a
   * click describes the screen as it was at the click, not after a keystroke
   * slipped in between. Otherwise a promise resolving to false when the script
   * does not validate, the error already set for the user.
   *
   * A frozen contract (booked deal, Product) prices its own script: the
   * read-only editor text never enters the request.
   */
  function _prepareScriptCalculation(report = message => { error.value = message }) {
    if (contractTermsLocked.value) return null
    if (script.value === validatedScript.value) {
      // The text went back to the last valid version after a failed attempt:
      // the declarations on screen describe it again.
      if (parseError.value) { parseError.value = null; checkedScript.value = script.value }
      return null
    }
    return validateScript().then(ok => {
      if (!ok) report(_scriptErrorMessage())
      return ok
    })
  }

  const hestonCalibrationPending = computed(() => globalParams.model === 'heston'
    && underlyings.value.some(u => u.smile_calibration?.explicit && u.smile_calibration.status === 'loading'
      && u.smile_calibration.key === surfaceCalibrationKey(u, 'heston', globalParams.T, globalParams.r)))

  let _preparationRevision=0
  function _prepareCalculation(report = message => { error.value = message }) {
    const revision=++_preparationRevision
    const activeReport=message=>{if(revision===_preparationRevision) report(message)}
    if (hestonCalibrationPending.value) {
      report('La calibration Heston est en cours. Relancez le Pricer dès qu’elle est appliquée.')
      return Promise.resolve(false)
    }
    if (editingProductTerms.value) {
      report('Conservez la nouvelle version des termes avant de calculer ou de transmettre ce produit.')
      return Promise.resolve(false)
    }
    const scriptReady=_prepareScriptCalculation(activeReport)
    const frozenLsv = globalParams.model === 'lsv' && !s.isPreStrike()
      && !yieldCurve.enabled && !_rateParams().sigma_r && globalParams.barrierMonitoring === 'weekly'
      && underlyings.value.every(u => u.vol_surface && !_buildDividendCurve(u).length
        && !Number(u.ccyh) && !(u.sigma_fx * u.rho_sfx))
    const items=underlyings.value.filter(u=>!frozenLsv && u.vol_surface && ['sabr','lsv'].includes(globalParams.model))
    if(!items.length) return scriptReady
    const context=()=>({model:globalParams.model,horizon:globalParams.T,rate:globalParams.r})
    const signature=()=>JSON.stringify([globalParams,script.value,paramOverrides,constatOverrides,
      corrMatrix.value,currentProduct.value,openedDeal.value?.id,
      underlyings.value.map(u=>[u.ticker,u.ccy,u.sigma])])
    const startingModelContext=JSON.stringify(context())
    return (async()=>{
      if(scriptReady && !(await scriptReady)) return false
      try {
        if(revision!==_preparationRevision) return false
        if(JSON.stringify(context())!==startingModelContext) throw Error('Le contexte a changé pendant la préparation. Relancez le calcul.')
        const initial=signature()
        for(const u of items) {
          if(revision!==_preparationRevision) return false
          if(signature()!==initial || !underlyings.value.includes(u)) throw Error('Le contexte a changé pendant la préparation. Relancez le calcul.')
          const live=context()
          await calibrateUnderlying(u,live.model,live.horizon,live.rate,context)
          if(u.smile_parameter_mode!=='manual' && u.smile_calibration?.status==='unqualified')
            throw Error('Calibration exploratoire non qualifiée : paramètres non appliqués. '
              +(u.smile_calibration.qualification?.reasons || []).join(' '))
        }
        if(revision!==_preparationRevision) return false
        if(signature()!==initial || items.some(u=>!underlyings.value.includes(u)
          || (u.smile_parameter_mode!=='manual' && (u.smile_calibration?.status!=='ready'
            || u.smile_calibration.key!==surfaceCalibrationKey(u,globalParams.model,globalParams.T,globalParams.r)))))
          throw Error('La calibration ne correspond plus au contexte courant. Relancez le calcul.')
        return true
      } catch(e) { activeReport(e.message); return false }
    })()
  }

  function _scriptErrorMessage() {
    if (script.value !== checkedScript.value || !parseError.value) {
      return 'Le script a changé pendant sa validation : relancez le calcul.'
    }
    const detail = Array.isArray(parseError.value)
      ? parseError.value.join('\n') : String(parseError.value)
    if (parseRequestFailed) return `Validation du script impossible : ${detail.split('\n')[0]}`
    return `Script non valide — corrigez-le dans l’onglet Script : ${detail.split('\n')[0]}`
  }

  /** For panels that build their own request (KID, EMT, comparators). */
  async function ensureScriptValidated() {
    const preparing = _prepareCalculation(() => {})
    return preparing ? preparing : true
  }

  // Snapshot of the inputs that actually produced a pricing run, captured at
  // run time so the "Résultats" summary stays accurate even if the user keeps
  // editing params afterward — it describes THIS price, not the current form.
  function _snapshotInputs() {
    const rates = _rateParams()
    return {
      underlyings: underlyings.value.map(u => ({
        ...JSON.parse(JSON.stringify(u)),
        name: u.name, ticker: u.ticker, ccy: u.ccy, sigma: u.sigma, q: u.q, rho_rS: u.rho_rS,
        dividendCurveEnabled: !!u.dividendCurveEnabled,
        dividendDecay: u.dividendDecay,
        dividendCurve: _buildDividendCurve(u),
        hestonFitUsed: globalParams.model === 'heston'
          ? _hestonEvidence(u)?.dossier?.heston_fit?.mode ?? null : null,
      })),
      corrMatrix: corrMatrix.value.map(row => [...row]),
      r: globalParams.r, T: globalParams.T, N: globalParams.N, seed: globalParams.seed,
      model: globalParams.model, antithetic: globalParams.antithetic,
      hestonUncalibrated: globalParams.model === 'heston'
        ? underlyings.value.filter(u=>!_hestonEvidence(u)).map(u=>u.name) : [],
      rateModel: globalParams.rateModel, sigma_r: rates.sigma_r * 100, a_r: rates.a_r,
      barrierMonitoring: globalParams.barrierMonitoring, stepsPerYear: globalParams.stepsPerYear,
      trade_date: globalParams.trade_date, strike_date: globalParams.strike_date,
      value_date: globalParams.value_date,
      // La dernière constatation telle qu'elle a été envoyée au moteur, pour
      // que l'écran l'affiche plutôt que de la redériver de la maturité en
      // années — qui la manquait de quelques jours.
      maturity_date: s._maturityDate(),
      payment_date: globalParams.payment_date,
      valuation_date: globalParams.valuation_date,
      yieldCurveEnabled: yieldCurve.enabled,
      paramsUsed: scriptParams.value.map(p => ({
        name: p.name, value: paramOverrides[p.name] ?? p.raw_default, is_pct: p.is_pct,
      })),
      hasConstats: scriptConstats.value.length > 0,
      hasStop: scriptHasStop.value,
      // Le produit lui-même, pas seulement ses réglages : le résumé écrit et
      // tout ce qui le consomme doivent décrire le payoff EXACT qui a produit
      // ce prix, calendrier compris.
      script: script.value,
      scriptName: currentScriptName.value || '',
      // Les CONSTAT DÉCLARÉS seulement : une entrée dormante décrirait dans le
      // résumé un échéancier que le produit ne porte plus.
      constats: JSON.parse(JSON.stringify(_declares(constatOverrides, scriptConstats.value))),
      deal_ccy: globalParams.deal_ccy,
      funding: fundingCurve.enabled
        ? { mode: fundingCurve.mode, level: fundingCurve.level,
            pillars: fundingCurve.pillars.map(x => ({ ...x })) }
        : null,
      yieldCurvePillars: yieldCurve.enabled
        ? yieldCurve.pillars.map(p => ({ T: p.T, rate: p.rate, label: p.label }))
        : [],
    }
  }

  Object.assign(s, { parseRequestFailed, parseScript, _installScriptValidation, validateScript, _prepareScriptCalculation, hestonCalibrationPending, _preparationRevision, _prepareCalculation, _scriptErrorMessage, ensureScriptValidated, _snapshotInputs })
}
