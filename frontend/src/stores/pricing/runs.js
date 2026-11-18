// Pricing, Greeks, profil, trajectoires, probabilités, backtest, comparateur, assistant de script et dictée.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { apiErrorMessage, apiFetch } from '../../utils/api.js'
import { ref } from 'vue'
import { _defaultUnderlying, _plausibleIsoDate } from './helpers.js'

export function installRuns(s) {
  const {
    _activeBookedContract, _authoritativeProductRequest, _baseBody, _buildConstats,
    _buildCorr, _buildUls, _buildUserParams, _constatsFrom, _contractCalendar,
    _contractUnderlyings, _fundingPayload, _maturityDate, _prepareCalculation, _pricingBody,
    _rateParams, _requestKey, _snapshotInputs, _startProgress, _stopProgress,
    adoptedGeneratedScriptText, backtest, contractTermsLocked, corrMatrix, error,
    globalParams, initialFixingName, isInLife, leftTab, loading, paths, proba, profile,
    result, resultIsStale, rightTab, script, scriptConstats, scriptGen,
    scriptGenerationProvenance, selectedGreeks, transcribeEngines, underlyings,
    usesDatedPricing, validateScript, variantInfo, yieldCurve,
  } = s

  /** Corps de requête de la valorisation en cours de vie — partagé par le
   *  prix et les Greeks, pour qu'ils décrivent forcément le même produit. */
  /**
   * Le corps d'une valorisation en cours de vie.
   *
   * Sur une VARIANTE d'avenant, il ne suffit pas d'envoyer ce que l'écran
   * affiche : le serveur rejouerait alors tout le passé sous les termes
   * nouveaux. Une barrière de rappel abaissée à 50 % trouverait une
   * constatation passée au-dessus et conclurait au rappel anticipé — le prix
   * d'une note déjà remboursée, ou un refus, selon les cas.
   *
   * Le corps porte donc les termes de l'ORIGINE — script, PARAM, calendrier —
   * et le bloc `variant` porte ceux de l'écran. Le passé se rejoue sous les
   * premiers, la vie restante se price sous les seconds. C'est cette asymétrie,
   * et elle seule, qui interdit à une variante de réécrire l'histoire.
   *
   * Une note neuve (roll) n'a pas de passé : son contexte est déjà celui de
   * l'écran, dates recalées comprises, et aucun bloc `variant` n'est nécessaire.
   */
  function _inLifeBody() {
    const frozen = _activeBookedContract()
    return _avecTermesDOrigine({
      script: frozen?.script ?? script.value,
      underlyings: _contractUnderlyings(frozen),
      corr_matrix: _buildCorr(),
      r: globalParams.r / 100,
      N: globalParams.N,
      model: globalParams.model,
      seed: globalParams.seed,
      antithetic: globalParams.antithetic,
      user_params: frozen?.user_params ?? _buildUserParams(),
      constats: frozen?.constats ?? _buildConstats(),
      strike_date: frozen?.strike_date ?? globalParams.strike_date,
      value_date: frozen?.value_date
        ?? globalParams.value_date ?? globalParams.strike_date,
      maturity_date: frozen?.maturity_date ?? _maturityDate(),
      payment_date: frozen ? frozen.payment_date : (globalParams.payment_date || null),
      valuation_date: globalParams.valuation_date,
      settlement_ccy: frozen?.settlement_ccy ?? globalParams.deal_ccy ?? 'EUR',
      frozen_schedule: _contractCalendar(frozen),
      yield_curve: yieldCurve.enabled
        ? yieldCurve.pillars.map(p => [p.T, p.rate / 100])
        : [],
      ..._fundingPayload(),
      barrier_monitoring: globalParams.barrierMonitoring,
      steps_per_year: globalParams.stepsPerYear,
      ..._rateParams(),
    })
  }

  /**
   * Sépare les termes du rejeu de ceux du pricing, quand une variante est
   * affichée. Hors variante, rend le corps inchangé.
   *
   * `base_pricing` vient du serveur (vue de variante) : il porte le script, les
   * PARAM en unités MOTEUR et le calendrier de l'ORIGINE. Les recalculer ici
   * demanderait de reparser le script du parent pour connaître ses `is_pct` —
   * une seconde voie de conversion, donc une divergence de plus.
   */
  function _avecTermesDOrigine(corps) {
    const v = variantInfo.value
    if (!v?.base) return corps
    return {
      ...corps,
      script: v.base.script,
      user_params: v.base.user_params,
      // Le serveur rend le calendrier de l'origine dans sa forme STOCKÉE :
      // il passe par la même conversion que celui de l'écran.
      constats: _constatsFrom(v.base.constats),
      variant: {
        script: corps.script,
        user_params: corps.user_params,
        constats: corps.constats,
        mode: v.mode || 'avenant',
      },
    }
  }

  function _validatePricingDates(request) {
    if (!initialFixingName.value) return
    const requireDate = (value, label) => {
      if (!value) throw new Error(`Renseignez ${label} dans Economics.`)
      const date = new Date(`${value}T00:00:00Z`)
      if (!_plausibleIsoDate(value) || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) {
        throw new Error(`Corrigez ${label} dans Economics : la date est invalide.`)
      }
    }
    requireDate(request.strike_date, 'la StartDate (date de strike)')
    for (const calendar of scriptConstats.value) {
      if (calendar.role === 'initial_fixing') continue
      const value = request.constats?.[calendar.name]
      if (calendar.kind === 'single') {
        requireDate(typeof value === 'string' ? value : value?.date, `la date de ${calendar.name}`)
      } else {
        requireDate(value?.first_observation_date, `la première observation de ${calendar.name}`)
        requireDate(value?.end_date, `la dernière observation de ${calendar.name}`)
        if (!value.frequency) throw new Error(`Renseignez la fréquence de ${calendar.name} dans Economics.`)
      }
    }
  }

  /** Valorisation en cours de vie : le passé est rejoué sur cours réels, seule
   *  la vie restante est simulée. Voir api/inlife.py pour pourquoi un simple
   *  « repartir du bon spot » ne suffirait pas sur un produit à mémoire. */
  async function runInLifePricing() {
    while (s.automaticMarketRequest) await s.automaticMarketRequest.promise
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    let request
    try { request = _inLifeBody(); _validatePricingDates(request) }
    catch (e) { error.value = e.message; leftTab.value = 'economics'; return }
    request.seed = 42
    const requestKey = _requestKey(request)
    const inputs = _snapshotInputs()
    inputs.seed = 42
    const revision = ++s._pricingRevision
    loading.value = true; error.value = null; result.value = null
    _startProgress((globalParams.N / 20000) * 350)
    try {
      request = await _authoritativeProductRequest(request)
      const res = await apiFetch('/api/price/in-life', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
      const data = await res.json()
      if (revision !== s._pricingRevision || requestKey !== _requestKey(_pricingBody())) {
        if (revision === s._pricingRevision) error.value = 'Les paramètres ont changé pendant le calcul. Relancez le pricing.'
        return
      }
      if (!res.ok) { error.value = apiErrorMessage(data, 'Erreur serveur'); return }
      if (data.early_recall) { error.value = data.message; return }
      result.value = { ...data, _inputs: inputs, _requestKey: requestKey }
      rightTab.value = 'results'
    } catch (e) { error.value = e.message }
    finally {
      if (revision === s._pricingRevision) { loading.value = false; _stopProgress() }
    }
  }

  async function runPricing() {
    while (s.automaticMarketRequest) await s.automaticMarketRequest.promise
    // Pricing, Greeks and booking validate the script first and stop on error.
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    if (usesDatedPricing()) return runInLifePricing()
    let request
    try { request = _pricingBody(); _validatePricingDates(request) }
    catch (e) { error.value = e.message; leftTab.value = 'economics'; return }
    request.seed = 42
    const requestKey = _requestKey(request)
    const inputs = _snapshotInputs()
    inputs.seed = 42
    const revision = ++s._pricingRevision
    loading.value = true; error.value = null; result.value = null
    _startProgress((globalParams.N / 20000) * 350)
    try {
      request = await _authoritativeProductRequest(request)
      const res = await apiFetch('/api/price', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...request,
          compute_greeks: false,
          selected_greeks: selectedGreeks.value,
        }),
      })
      if (revision !== s._pricingRevision || requestKey !== _requestKey(_pricingBody())) {
        if (revision === s._pricingRevision) error.value = 'Les paramètres ont changé pendant le calcul. Relancez le pricing.'
        return
      }
      if (!res.ok) { const err = await res.json(); error.value = apiErrorMessage(err, 'Erreur serveur') }
      else { result.value = { ...(await res.json()), _inputs: inputs, _requestKey: requestKey }; rightTab.value = 'results' }
    } catch (e) { error.value = e.message }
    finally {
      if (revision === s._pricingRevision) { loading.value = false; _stopProgress() }
    }
  }

  // ── Spread émetteur implicite ─────────────────────────────────────
  const impliedFunding = ref(null)

  /** Le calcul à l'envers : on donne le prix de marché, on lit le spread qui
   *  le reproduit. C'est la question qu'on se pose vraiment devant une ligne
   *  de secondaire — pas « que vaut-elle pour moi » mais « à quel spread le
   *  marché la traite ». N'a de sens qu'en cours de vie. */
  async function runImpliedFunding(prixCiblePct) {
    if (!isInLife()) {
      error.value = 'Le spread implicite se lit sur une valorisation en cours de vie : '
                  + 'renseignez une date de valorisation postérieure au strike.'
      return
    }
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    loading.value = true; error.value = null; impliedFunding.value = null
    _startProgress((globalParams.N / 20000) * 3500)
    try {
      const res = await apiFetch('/api/price/implied-funding', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // La bissection reprice une dizaine de fois : à 20 000 chemins ce
        // serait quatre minutes pour un chiffre qu'on lit à quelques bps près.
        // Même arbitrage que le solveur de paramètres, qui tourne à 8 000.
        body: JSON.stringify({ ..._inLifeBody(),
                                N: Math.min(globalParams.N, 8000),
                                target_price: prixCiblePct / 100 }),
      })
      const data = await res.json()
      if (!res.ok) { error.value = apiErrorMessage(data, 'Erreur serveur'); return }
      impliedFunding.value = data
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Greeks ────────────────────────────────────────────────────────
  async function runGreeks() {
    if (!result.value || !selectedGreeks.value.length) return
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    if (resultIsStale.value) {
      error.value = 'Le prix est périmé : relancez le pricing avant de calculer les Greeks.'
      return
    }
    const enCours = usesDatedPricing()
    const request = {
      ..._pricingBody(),
      // Reprendre le tirage du prix affiché pour que les différences finies
      // mesurent le bump, pas un nouveau bruit Monte Carlo.
      seed: 42,
      compute_greeks: true,
      selected_greeks: selectedGreeks.value,
    }
    const requestKey = _requestKey(request)
    const revision = ++s._pricingRevision
    loading.value = true; error.value = null
    _startProgress(selectedGreeks.value.length * (globalParams.N / 20000) * 400)
    try {
      // Même bascule que le prix : en cours de vie, les sensibilités se
      // calculent sur la jambe résiduelle. Passer par /api/price bumpait le
      // produit NEUF depuis t=0 — des Greeks d'émission affichés à côté d'un
      // mark-to-market, sans rapport avec le chiffre au-dessus.
      const res = await apiFetch(enCours ? '/api/price/in-life' : '/api/price', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
      if (revision !== s._pricingRevision || result.value?._requestKey !== requestKey
          || requestKey !== _requestKey(_pricingBody())) {
        if (revision === s._pricingRevision) error.value = 'Les paramètres ont changé pendant le calcul. Relancez le pricing.'
        return
      }
      if (!res.ok) { const err = await res.json(); error.value = apiErrorMessage(err, 'Erreur serveur') }
      else {
        const data = await res.json()
        result.value = {
          ...result.value,
          greeks: data.greeks,
          // Use the spot/strike ratios from this Greek calculation, not from
          // an earlier price which may have used different market data.
          _greekDated: enCours,
          _greekSpotRatios: enCours ? data.past?.performances : null,
          _greekPreStrike: enCours && !!data.pre_strike,
        }
        rightTab.value = 'greeks'
      }
    } catch (e) { error.value = e.message }
    finally {
      if (revision === s._pricingRevision) { loading.value = false; _stopProgress() }
    }
  }

  // ── Payoff Profile ────────────────────────────────────────────────
  async function runProfile() {
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    loading.value = true; error.value = null
    _startProgress(800)
    try {
      const res = await apiFetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(_baseBody()),
      })
      if (!res.ok) { const err = await res.json(); error.value = apiErrorMessage(err) }
      else { profile.value = await res.json(); rightTab.value = 'profile' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── MC Paths ──────────────────────────────────────────────────────
  async function runPaths() {
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    loading.value = true; error.value = null
    _startProgress(1500)
    try {
      const res = await apiFetch('/api/paths', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ..._baseBody(), N_stat: 500, N_display: 50 }),
      })
      if (!res.ok) { const err = await res.json(); error.value = apiErrorMessage(err) }
      else { paths.value = await res.json(); rightTab.value = 'paths' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Probability analysis ──────────────────────────────────────────
  async function runProba() {
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    loading.value = true; error.value = null
    _startProgress(2000)
    try {
      const res = await apiFetch('/api/proba', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ..._baseBody(), N: 5000 }),
      })
      if (!res.ok) { const err = await res.json(); error.value = apiErrorMessage(err) }
      else { proba.value = await res.json(); rightTab.value = 'proba' }
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Historical backtest ───────────────────────────────────────────
  let backtestRevision = 0
  async function runBacktest(params = {}) {
    const preparing = _prepareCalculation()
    if (preparing && !(await preparing)) return
    const revision = ++backtestRevision
    const inputs = JSON.stringify(_snapshotInputs())
    const isCurrent = () => revision === backtestRevision && inputs === JSON.stringify(_snapshotInputs())
    loading.value = true; error.value = null; backtest.value = null
    _startProgress(8000)
    try {
      const res = await apiFetch('/api/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ..._baseBody(),
          start_date: params.start_date || null,
          end_date: params.end_date || null,
          freq: params.freq ?? 21,
          invest_pct: params.invest_pct ?? (result.value ? result.value.price * 100 : 100),
          rf_rate: params.rf_rate ?? 2.0,
          history_mode: params.history_mode ?? 'following',
          max_delay_days: params.max_delay_days ?? 10,
        }),
      })
      const payload = await res.json()
      if (!isCurrent()) return
      if (!res.ok) error.value = apiErrorMessage(payload)
      else { backtest.value = payload; rightTab.value = 'backtest' }
    } catch (e) { if (isCurrent()) error.value = e.message }
    finally { if (revision === backtestRevision) { loading.value = false; _stopProgress() } }
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

  let comparatorRevision = 0
  async function runBacktestCompare(candidates, params = {}, contextCurrent = () => true) {
    const preparing = _prepareCalculation(message => { comparatorError.value = message })
    if (preparing && !(await preparing)) return
    const revision = ++comparatorRevision, inputs = JSON.stringify(_snapshotInputs())
    const isCurrent = () => revision === comparatorRevision && contextCurrent() && inputs === JSON.stringify(_snapshotInputs())
    comparatorLoading.value = true; comparatorError.value = ''; comparator.value = null
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
          // Le comparateur construit son corps à la main (candidats, fenêtre
          // d'historique) : sans ces quatre champs son calendrier se résout
          // autrement que celui du prix — et échoue net dès qu'un CONSTAT
          // porte un décalage de règlement.
          strike_date: globalParams.strike_date || null,
          value_date: globalParams.value_date || null,
          payment_date: globalParams.payment_date || null,
          settlement_ccy: globalParams.deal_ccy || null,
          anchor: globalParams.strike_date || globalParams.value_date || null,
          basket_size: params.basket_size || 1,
          shortlist_n: params.shortlist_n || 8,
          start_date: params.start_date || null,
          end_date: params.end_date || null,
          freq: params.freq ?? 21,
          invest_pct: params.invest_pct ?? 100,
          rf_rate: params.rf_rate ?? 2.0,
          history_mode: params.history_mode ?? 'following',
          max_delay_days: params.max_delay_days ?? 10,
        }),
      })
      const payload = await res.json()
      if (!isCurrent()) return
      if (!res.ok) throw new Error(apiErrorMessage(payload))
      comparator.value = payload
    } catch (e) {
      if (isCurrent()) comparatorError.value = e.message
    } finally {
      if (revision === comparatorRevision) comparatorLoading.value = false
    }
  }

  // Replace the current underlyings/correlation with a candidate basket
  // picked from the comparator, then refresh σ/q for the new tickers.
  async function adoptBasket(tickers, names, corrMat) {
    if (contractTermsLocked.value) {
      throw new Error('Le panier est figé sur un deal booké. Dupliquez le produit pour le modifier.')
    }
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
    await s.loadYfAll()
    corrMatrix.value = corrMat.map(row => [...row])
  }

  // Business context and adoption stay here; the shared workbench owns AI calls.
  function scriptAssistantPayload({ description, refine = false, currentScript = '' }) {
    return { description, underlyings: _buildUls(), corr_matrix: _buildCorr(),
      r: globalParams.r / 100, T: globalParams.T || null, user_params: _buildUserParams({ allowMissing: true }),
      current_script: refine ? currentScript : '', refine }
  }

  // ── Dictée ─────────────────────────────────────────────────────────
  // Pas de `force` ici, contrairement aux moteurs de scripting : un
  // `ollama pull` change la liste des modèles en cours de session, alors qu'un
  // `pip install faster-whisper` impose de toute façon un redémarrage du
  // serveur — donc un rechargement de la page.
  async function loadTranscribeEngines(force = false) {
    if (transcribeEngines.value && !force) return transcribeEngines.value
    try {
      const res = await apiFetch('/api/script/transcribe/engines')
      if (res.ok) transcribeEngines.value = await res.json()
    } catch { /* le micro restera grisé */ }
    return transcribeEngines.value
  }

  // Télécharge et charge le moteur hors dictée. Rend { error } en cas d'échec.
  // Sans cette étape le premier clic sur le micro déclenchait 480 Mo au milieu
  // d'une requête de transcription, qui n'y survivait pas.
  async function prepareTranscribe() {
    try {
      const res = await apiFetch('/api/script/transcribe/prepare', { method: 'POST' })
      const data = await res.json()
      if (!res.ok) return { error: data.detail || 'Erreur serveur' }
      await loadTranscribeEngines(true)
      return data
    } catch (e) {
      return { error: e.message }
    }
  }

  // Rend { text } ou { error }. L'erreur est rédigée côté serveur, en français
  // et pour l'utilisateur (paquet absent, poids non téléchargés, décodage) :
  // on la remonte telle quelle plutôt que d'en fabriquer une seconde.
  async function transcribeAudio(blob) {
    try {
      const form = new FormData()
      // Le nom de fichier porte l'extension dont le décodeur se sert pour
      // choisir son démultiplexeur — un blob sans nom arrive en `.bin`.
      form.append('audio', blob, 'dictee.webm')
      const res = await apiFetch('/api/script/transcribe', { method: 'POST', body: form })
      const data = await res.json()
      return res.ok ? data : { error: data.detail || 'Erreur serveur' }
    } catch (e) {
      return { error: e.message }
    }
  }

  // Adoption explicite : le script ne descend dans l'éditeur que sur action de
  // l'utilisateur. Un script qui atterrirait tout seul, c'est un produit faux
  // qui part en cotation.
  function adoptGeneratedScript({ warningsAcknowledged = false } = {}) {
    if (contractTermsLocked.value) return
    if (!scriptGen.value?.script) return
    if (scriptGen.value.adoption_requires_acknowledgement && !warningsAcknowledged) return
    script.value = scriptGen.value.script
    adoptedGeneratedScriptText.value = scriptGen.value.script
    scriptGenerationProvenance.value = {
      generation_id: scriptGen.value.generation_id,
      generated_at: scriptGen.value.generated_at,
      provider: scriptGen.value.provider,
      requested_model: scriptGen.value.requested_model,
      effective_model: scriptGen.value.effective_model || scriptGen.value.model,
      prompt_version: scriptGen.value.prompt_version,
      prompt_customized: scriptGen.value.prompt_customized,
      base_hash: scriptGen.value.base_hash,
      examples_version: scriptGen.value.examples_version,
      examples: scriptGen.value.examples || [],
      attempts: scriptGen.value.attempts || [],
      script_sha256: scriptGen.value.script_sha256,
      checks_status: scriptGen.value.checks_status,
      pricing_check: scriptGen.value.pricing_check,
      payoff_qualification: scriptGen.value.payoff_qualification
        ? JSON.parse(JSON.stringify(scriptGen.value.payoff_qualification)) : { status: 'STRUCTURAL_ONLY' },
      warnings_acknowledged: !!warningsAcknowledged,
      adopted_script_text: scriptGen.value.script,
      modified_after_adoption: false,
    }
    // Adopting is an explicit change of the script: a changed declaration
    // carries its new value over, exactly as on Ctrl+S.
    validateScript()
  }

  Object.assign(s, { _inLifeBody, _avecTermesDOrigine, _validatePricingDates, runInLifePricing, runPricing, impliedFunding, runImpliedFunding, runGreeks, runProfile, runPaths, runProba, backtestRevision, runBacktest, comparator, comparatorError, comparatorLoading, comparatorRevision, runBacktestCompare, adoptBasket, scriptAssistantPayload, loadTranscribeEngines, prepareTranscribe, transcribeAudio, adoptGeneratedScript })
}
