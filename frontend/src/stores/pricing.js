import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { apiFetch } from '../utils/api.js'
import { calculerDelta, contexteDepuisCorps } from '../composables/useVariantDelta.js'
import { courbeDividende } from '../composables/useDividendCurve.js'

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

  /**
   * Aligne les surcharges sur ce que le script DÉCLARE, sans rien détruire.
   *
   * Règle du projet : le script déclare des noms, le deal porte les valeurs.
   * Une valeur saisie est une donnée de term sheet, pas une dérivée du texte —
   * une manipulation de texte ne doit donc jamais la détruire.
   *
   * Un nom qui disparaît laisse sa valeur DORMANTE : plus rien ne la lit
   * (`_buildUserParams` et `_buildConstats` parcourent les déclarations, pas
   * les entrées), mais si le nom revient, la valeur revient avec lui. Le coût
   * est de quelques centaines d'octets ; le bénéfice est qu'un renommage par
   * erreur, un copier-coller ou une frappe malheureuse ne coûtent plus une
   * ressaisie de term sheet.
   */
  function _syncParamOverrides() {
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
      // Sans ajustement ni décalage par défaut : c'est déjà ce que le parseur
      // suppose faute de valeur, donc rien ne bouge pour un script existant.
      // Un term sheet qui dit autre chose le dit maintenant explicitement.
      convention: 'none', settlement_lag: 0,
    })
  }

  function _tenorStr(t) {
    return (t && t.value) ? `${t.value}${t.unit}` : null
  }

  /** Même règle que `_syncParamOverrides` : on complète, on ne supprime pas. */
  function _syncConstatOverrides() {
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
    // Échange final des flux. Vide, le remboursement est actualisé à la
    // maturité — ce qui surestime la note des jours de règlement.
    payment_date: '',
    // Date à laquelle on veut la valeur. Vide ou égale au strike, on price à
    // l'émission ; postérieure, on rejoue le passé et on ne simule que la vie
    // restante. Le mode ne se choisit pas, il se déduit de cette date.
    valuation_date: '',
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
    // Ancrage sur le taux sans risque de l'écran : la courbe se dérive alors
    // de r par une pente amortie plutôt que de se saisir pilier par pilier.
    // Voir `courbeAncree`. Désactivé par défaut — les niveaux saisis à la main
    // et les scénarios restent le comportement d'origine.
    ancree: false,
    ecart: 120,   // prime de terme totale, en bps
    tau: 4.0,     // années pour en parcourir les deux tiers
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

  // ── Courbe de funding (spread émetteur) ───────────────────────────
  // Distincte de la courbe de taux, et pas par coquetterie : un spread
  // émetteur n'entre QUE dans l'actualisation. Le crédit de l'émetteur ne
  // déplace pas le forward du sous-jacent. Fondues ensemble, on obtiendrait le
  // signe inverse — voir engine._funding_df_arr.
  //
  // Deux modes, parce que c'est ainsi qu'on travaille : un niveau unique quand
  // on connaît le funding de la contrepartie et que ça suffit, une courbe par
  // pilier quand elle a une forme — ce qui arrive vite sur un émetteur tendu,
  // où le court coûte plus cher que le long.
  const fundingCurve = reactive({
    enabled: false,
    mode: 'flat',          // 'flat' | 'pillars'
    level: 1.50,           // en %, appliqué à tous les piliers
    pillars: [
      { label: '3M',  T: 0.25, spread: 1.50 },
      { label: '6M',  T: 0.5,  spread: 1.50 },
      { label: '1Y',  T: 1.0,  spread: 1.50 },
      { label: '2Y',  T: 2.0,  spread: 1.50 },
      { label: '3Y',  T: 3.0,  spread: 1.50 },
      { label: '5Y',  T: 5.0,  spread: 1.50 },
      { label: '7Y',  T: 7.0,  spread: 1.50 },
      { label: '10Y', T: 10.0, spread: 1.50 },
    ],
  })

  /** Ce que la requête doit porter : un niveau plat OU des piliers, jamais
   *  les deux — côté moteur la courbe l'emporte, autant ne pas l'ambiguïser. */
  function _fundingPayload() {
    if (!fundingCurve.enabled) return { funding_curve: [], funding_spread: 0 }
    if (fundingCurve.mode === 'pillars') {
      return {
        funding_curve: fundingCurve.pillars.map(p => [p.T, p.spread / 100]),
        funding_spread: 0,
      }
    }
    return { funding_curve: [], funding_spread: (Number(fundingCurve.level) || 0) / 100 }
  }

  // ── Greeks selection ──────────────────────────────────────────────
  const greekSel = reactive({
    delta: true, gamma: false, vega: true,
    theta: true, rho: false, corr: false,
    // Sensibilité au spread émetteur. Décochée par défaut comme le rho : sur
    // un produit non émis elle n'a pas d'objet, elle prend son sens sur une
    // valorisation de secondaire.
    credit: false,
  })
  const selectedGreeks = computed(() => Object.keys(greekSel).filter(k => greekSel[k]))

  // ── Current script DB identity ────────────────────────────────────
  const currentScriptId   = ref(null)
  // ── Variante ──────────────────────────────────────────────────────
  // Renseigné quand l'écran affiche une DÉCLINAISON d'un deal plutôt que le
  // deal lui-même. `ecarts` vient du serveur : c'est le delta stocké, enrichi
  // de la valeur d'origine. Le recalculer ici ferait diverger ce qu'on colore
  // de ce qui a servi à pricer.
  const variantInfo = ref(null)   // {id, parent_id, title, mode, ecarts[], delta, parent}

  /**
   * Oublie la déclinaison affichée.
   *
   * `variantInfo` décrit LE PRODUIT ACTUELLEMENT DANS LE STORE. Tout ce qui
   * remplace ce produit doit donc le relâcher — sans quoi l'état « modifié »
   * continue de comparer l'écran au parent d'une variante qu'on ne regarde
   * plus, et l'avertissement de sortie se redéclenche page après page.
   *
   * Appelé aussi quand l'utilisateur confirme qu'il quitte sans enregistrer :
   * il vient de dire que ces modifications sont abandonnées, les lui
   * représenter à la navigation suivante serait lui redemander ce qu'il a déjà
   * tranché. Revenir sur la déclinaison la rechargera depuis le serveur, donc
   * sans les modifications abandonnées — ce qui est exactement ce qu'il a
   * demandé.
   */
  function relacherVariante() {
    variantInfo.value = null
  }
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

  // La dérivation vit dans useDividendCurve : l'écran d'appel d'offres en a
  // besoin avec SON horizon, et deux implémentations d'une convention de
  // bucket finiraient par décaler la courbe d'un an sans rien signaler.
  const _buildDividendCurve = (u) => courbeDividende(u, globalParams.T)

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
      if (c.kind === 'single' || typeof v === 'string') {
        out[c.name] = v
      } else {
        out[c.name] = {
          start_date: v.start_date, end_date: v.end_date, roll_date: v.roll_date,
          frequency: _tenorStr(v.frequency), stub: v.stub,
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
  function _baseBody() {
    return _avecTermesDOrigine({
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
      ..._fundingPayload(),
      barrier_monitoring: globalParams.barrierMonitoring,
      constats: _buildConstats(),
      // Les trois dates et la devise, exactement comme pour la valorisation en
      // cours de vie. Elles ne partaient pas d'ici : le serveur recevait un
      // décalage de règlement sans calendrier de devise pour le compter et
      // refusait le calcul — c'est ce qui cassait les Greeks dès qu'un CONSTAT
      // portait un règlement.
      strike_date: globalParams.strike_date || null,
      value_date: globalParams.value_date || null,
      payment_date: globalParams.payment_date || null,
      settlement_ccy: globalParams.deal_ccy || null,
      // Ce qui fait basculer une analytique sur la vie restante. Absentes,
      // elle décrit le produit à l'émission — comportement historique.
      valuation_date: globalParams.valuation_date || null,
      maturity_date: _maturityDate(),
      // Le calendrier CONSTAT porte des dates absolues ; le moteur veut des
      // fractions d'année depuis l'origine de son axe, qui est la date de
      // STRIKE — là où le niveau initial se constate. Repli sur la value date
      // pour les produits qui n'en déclarent pas.
      anchor: globalParams.strike_date || globalParams.value_date || null,
    })
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
        // Une erreur de parse veut dire « je ne sais pas ce que ce script
        // déclare », pas « il ne déclare rien ». On garde donc la dernière
        // lecture valide et on ne synchronise PAS : vider les déclarations
        // puis synchroniser effaçait toutes les saisies, et l'éditeur repasse
        // par un état non parsable à chaque ligne qu'on ajoute — il suffit
        // d'une pause de 500 ms au milieu d'un `SET`.
        //
        // Rien ne peut être valorisé avec des déclarations périmées : le
        // bouton Pricer est désactivé tant que `parseError` est renseigné.
        parseError.value = data.errors
        return
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
      // La dernière constatation telle qu'elle a été envoyée au moteur, pour
      // que l'écran l'affiche plutôt que de la redériver de la maturité en
      // années — qui la manquait de quelques jours.
      maturity_date: _maturityDate(),
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

  // ── Price ─────────────────────────────────────────────────────────
  /** Vrai quand la date de valorisation demande un rejeu du passé. */
  function isInLife() {
    const v = globalParams.valuation_date
    return !!(v && globalParams.strike_date && v > globalParams.strike_date)
  }

  /** Maturité déduite : depuis la constatation initiale, qui est l'origine de
   *  la diffusion. */
  function _maturityDate() {
    // Un calendrier CONSTAT dit la dernière constatation à la journée près.
    // La déduire de la maturité en années la manquait de plusieurs jours —
    // 19/06 au lieu du 14/06 sur un trois ans mensuel — parce que T×365,25
    // n'est pas une date d'anniversaire.
    const fins = scriptConstats.value
      .filter(c => c.kind !== 'single')
      .map(c => constatOverrides[c.name]?.end_date)
      .filter(Boolean)
    if (fins.length) return fins.reduce((a, b) => (b > a ? b : a))
    if (!globalParams.strike_date || !globalParams.T) return null
    const d = new Date(globalParams.strike_date)
    d.setDate(d.getDate() + Math.round(globalParams.T * 365.25))
    return d.toISOString().split('T')[0]
  }

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
    return _avecTermesDOrigine({
      script: script.value,
      underlyings: _buildUls(),
      corr_matrix: _buildCorr(),
      r: globalParams.r / 100,
      N: globalParams.N,
      model: globalParams.model,
      seed: globalParams.seed,
      antithetic: globalParams.antithetic,
      user_params: _buildUserParams(),
      constats: _buildConstats(),
      strike_date: globalParams.strike_date,
      value_date: globalParams.value_date || globalParams.strike_date,
      maturity_date: _maturityDate(),
      payment_date: globalParams.payment_date || null,
      valuation_date: globalParams.valuation_date,
      settlement_ccy: globalParams.deal_ccy || 'EUR',
      yield_curve: yieldCurve.enabled
        ? yieldCurve.pillars.map(p => [p.T, p.rate / 100])
        : [],
      ..._fundingPayload(),
      barrier_monitoring: globalParams.barrierMonitoring,
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

  /** Valorisation en cours de vie : le passé est rejoué sur cours réels, seule
   *  la vie restante est simulée. Voir api/inlife.py pour pourquoi un simple
   *  « repartir du bon spot » ne suffirait pas sur un produit à mémoire. */
  async function runInLifePricing() {
    loading.value = true; error.value = null; result.value = null
    _startProgress((globalParams.N / 20000) * 350)
    try {
      const res = await apiFetch('/api/price/in-life', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(_inLifeBody()),
      })
      const data = await res.json()
      if (!res.ok) { error.value = data.detail || 'Erreur serveur'; return }
      if (data.early_recall) { error.value = data.message; return }
      result.value = { ...data, _inputs: _snapshotInputs() }
      rightTab.value = 'results'
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  async function runPricing() {
    if (isInLife()) return runInLifePricing()
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
      if (!res.ok) { error.value = data.detail || 'Erreur serveur'; return }
      impliedFunding.value = data
    } catch (e) { error.value = e.message }
    finally { loading.value = false; _stopProgress() }
  }

  // ── Greeks ────────────────────────────────────────────────────────
  async function runGreeks() {
    if (!result.value || !selectedGreeks.value.length) return
    loading.value = true; error.value = null
    _startProgress(selectedGreeks.value.length * (globalParams.N / 20000) * 400)
    try {
      // Même bascule que le prix : en cours de vie, les sensibilités se
      // calculent sur la jambe résiduelle. Passer par /api/price bumpait le
      // produit NEUF depuis t=0 — des Greeks d'émission affichés à côté d'un
      // mark-to-market, sans rapport avec le chiffre au-dessus.
      const enCours = isInLife()
      const res = await apiFetch(enCours ? '/api/price/in-life' : '/api/price', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...(enCours ? _inLifeBody() : _baseBody()),
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

  // ── Yahoo Finance data loader ─────────────────────────────────────
  const yfStatus = ref('')

  /** Profil de dividende d'un titre à une date donnée : rendement déclaré,
   *  rendement implicite lu dans l'écart des séries, et les détachements qui
   *  fondent le chiffre. `asof` vide = aujourd'hui. */
  async function loadDividendProfile(ticker, asof) {
    try {
      const params = new URLSearchParams({ ticker })
      if (asof) params.set('asof', asof)
      const res = await apiFetch(`/api/finance/dividends?${params}`)
      return res.ok ? await res.json() : null
    } catch { return null }
  }

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
      // Le dividende ne vient plus du champ instantané de Yahoo : il est
      // reconstruit à la DATE DE VALORISATION, avec le détail des
      // détachements qui le fondent (voir services/market_data.dividend_profile).
      const div = await loadDividendProfile(tk, globalParams.valuation_date || null)
      const q = div?.ok ? div.yield_declared : (data.div_yields?.[tk] ?? 0)
      if (vol != null) {
        underlyings.value[idx].sigma = Math.round(vol * 1000) / 10
        underlyings.value[idx].alpha = Math.round(vol * 1000) / 10
        underlyings.value[idx].q     = Math.round(q * 10000) / 100
        underlyings.value[idx].name  = tk
        underlyings.value[idx].dividendProfile = div?.ok ? div : null
        const suffixe = div?.ok
          ? (div.pays_dividends
              ? ` · ${div.dividends.length} détachement(s)` + (div.suspect ? ' ⚠ écart de sources' : '')
              : ' · ne verse pas de dividende')
          : ''
        yfStatus.value = `✓ ${tk} — σ=${(vol*100).toFixed(1)}%, q=${(q*100).toFixed(2)}% · ${data.n_obs} obs.${suffixe}`
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

  /** Clôtures NUES à une date, par ticker : { TICKER: {close, date} }.
   *
   *  Le fixing d'un produit structuré est la clôture non ajustée — celle que
   *  le term sheet cite. Cet écran lisait le magasin de prix AMC, qui est
   *  volontairement auto-ajusté (voir core/amc_prices.py) parce qu'il sert au
   *  FIFO et à l'attribution de portefeuille, où la série total-return est la
   *  bonne. Résultat : des spots déflatés des dividendes versés depuis, donc
   *  en contradiction avec le niveau que le moteur a réellement utilisé — et
   *  vides tant qu'on n'avait pas semé le magasin à la main.
   *
   *  On lit désormais la même source que le pricer, à la demande. */
  async function loadStrikeCloses(tickers, jour) {
    const tk = [...new Set((tickers || []).filter(Boolean))]
    if (!tk.length || !jour) return {}
    // Marge arrière : une date de strike un week-end ou un férié n'a pas de
    // cours, c'est la dernière clôture connue qui fait foi — même convention
    // que le rejeu côté serveur.
    const debut = new Date(jour)
    debut.setDate(debut.getDate() - 10)
    const q = new URLSearchParams({ tickers: tk.join(','),
                                     start: debut.toISOString().split('T')[0], end: jour })
    try {
      const res = await fetch(`/api/finance/hist_prices?${q}`)
      if (!res.ok) return {}
      const data = await res.json()
      const dates = data.dates || []
      let idx = -1
      for (let i = 0; i < dates.length; i++) { if (dates[i] <= jour) idx = i; else break }
      if (idx < 0) return {}
      const out = {}
      for (const t of tk) {
        const serie = data.prices?.[t]
        if (serie && serie[idx]) out[t] = { close: serie[idx], date: dates[idx] }
      }
      return out
    } catch { return {} }
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
    relacherVariante()
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
    relacherVariante()
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
    relacherVariante()
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
      // La date de paiement AUSSI, et c'est la troisième du même term sheet :
      // l'oublier laissait le champ vide dans le masque de booking, où une
      // proposition en J+3 depuis la maturité venait le remplir. Cette date-là
      // n'est pas celle de l'AO — et `payment_date` fait partie des termes
      // contractuels gelés, donc le booking était refusé pour un écart que
      // personne n'avait saisi. Elle date l'échange final des flux : elle se
      // reprend, elle ne se recalcule pas.
      payment_date: p.payment_date || globalParams.payment_date,
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

  async function loadFromDb(data) {
    // Charger une ORIGINE efface toute variante affichée : sans ça, la barre
    // de déclinaison survivrait à la navigation et colorerait des champs par
    // rapport à un parent qui n'est plus à l'écran.
    relacherVariante()
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
      // Le panier et sa calibration. Fusionnés sur un sous-jacent par défaut
      // pour qu'un champ ajouté après la sauvegarde arrive avec sa valeur par
      // défaut plutôt qu'en undefined. Absents des scripts enregistrés avant
      // que ce soit sauvegardé : on garde alors ce qui est à l'écran.
      if (Array.isArray(saved.underlyings) && saved.underlyings.length) {
        underlyings.value = saved.underlyings.map(
          (u, i) => ({ ..._defaultUnderlying(i + 1), ...u }))
      }
      if (Array.isArray(saved.corr_matrix) && saved.corr_matrix.length) {
        corrMatrix.value = saved.corr_matrix.map(row => [...row])
      }
      if (saved.funding) {
        fundingCurve.enabled = !!saved.funding.enabled
        fundingCurve.mode = saved.funding.mode || 'flat'
        fundingCurve.level = saved.funding.level ?? 1.5
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

    _clearResults()
  }

  function _scriptBody() {
    return {
      script_text: script.value,
      params_json: JSON.stringify({ ...paramOverrides }),
      constats_json: JSON.stringify(JSON.parse(JSON.stringify(constatOverrides))),
      // Tout ce qu'il faut pour retrouver le pricing tel quel, pas seulement
      // le script. Il manquait les trois dates qui définissent la vie du
      // produit, le panier et sa calibration, et la corrélation : rouvrir un
      // script sauvegardé rendait un écran qu'il fallait resaisir sous-jacent
      // par sous-jacent, avec des dates repartant d'aujourd'hui — donc un
      // autre prix, sans que rien ne le signale.
      global_params_json: JSON.stringify({
        r: globalParams.r, T: globalParams.T, N: globalParams.N,
        seed: globalParams.seed, model: globalParams.model,
        antithetic: globalParams.antithetic, deal_ccy: globalParams.deal_ccy,
        rateModel: globalParams.rateModel, sigma_r: globalParams.sigma_r, a_r: globalParams.a_r,
        barrierMonitoring: globalParams.barrierMonitoring,
        trade_date: globalParams.trade_date,
        strike_date: globalParams.strike_date,
        value_date: globalParams.value_date,
        payment_date: globalParams.payment_date,
        valuation_date: globalParams.valuation_date,
        underlyings: underlyings.value.map(u => ({ ...u })),
        corr_matrix: corrMatrix.value.map(row => [...row]),
        // Le spread émetteur fait partie des hypothèses de valorisation au
        // même titre que la vol : sans lui, rouvrir le script rendrait un
        // autre prix sans que rien ne le signale.
        funding: { enabled: fundingCurve.enabled, mode: fundingCurve.mode,
                    level: fundingCurve.level,
                    pillars: fundingCurve.pillars.map(x => ({ ...x })) },
        yield_curve_enabled: yieldCurve.enabled,
        yield_curve_pillars: yieldCurve.pillars.map(x => ({ ...x })),
      }),
    }
  }

  /**
   * Enregistre la déclinaison affichée — en écrivant ses ÉCARTS, pas une copie.
   *
   * Sans ça, travailler sur une variante puis revenir dessus perdait tout :
   * l'écran chargeait le contexte du serveur, qui ne portait aucune des
   * modifications restées locales.
   *
   * Les écarts sont déduits en comparant l'état courant au contexte de
   * l'origine — voir useVariantDelta pour ce qui compte comme un écart, et
   * surtout pour ce qui n'en est pas un.
   */
  /**
   * Les écarts que l'écran porte À CET INSTANT, contre l'origine.
   *
   * Dérivé plutôt que suivi à la main : un drapeau « modifié » qu'il faut
   * penser à lever se désynchronise au premier champ ajouté, et c'est
   * précisément le genre d'oubli qui fait perdre du travail sans un mot.
   * Ici l'état ne peut pas mentir — il EST la comparaison.
   */
  const deltaCourant = computed(() => {
    const v = variantInfo.value
    if (!v?.parent) return null
    return calculerDelta(v.parent, _contexteAPlat(), {
      params: scriptParams.value.map(x => x.name),
      constats: scriptConstats.value.map(x => x.name),
    })
  })

  /**
   * Le contexte courant, avec les sous-jacents dans la forme d'INSTANTANÉ.
   *
   * La fiche brute de l'écran ne porte pas sa courbe de dividende : celle-ci se
   * DÉRIVE de `q` et du taux de décroissance, et seulement si la courbe est
   * activée. Un titre ajouté à une note neuve arriverait donc au moteur sans
   * dividende, avec un prix parfaitement plausible.
   *
   * On la dérive donc ici, dans la forme que `_engine_underlyings` sait relire
   * côté serveur — celle que produit déjà `_snapshot_underlying` pour la
   * valorisation en cours de vie. C'est ce qui permet au serveur de n'avoir
   * QU'UN convertisseur : une seconde voie, même soignée, finit toujours par
   * perdre un champ que la première gère.
   */
  /** Les entrées d'une table de surcharges dont le nom est encore déclaré. */
  function _declares(surcharges, declarations) {
    const noms = new Set(declarations.map(d => d.name))
    return Object.fromEntries(
      Object.entries(surcharges).filter(([nom]) => noms.has(nom)))
  }

  function _contexteAPlat() {
    const ctx = contexteDepuisCorps(_scriptBody())
    const uls = ctx.global?.underlyings
    if (Array.isArray(uls)) {
      ctx.global.underlyings = uls.map(u => ({
        ...u,
        dividendCurve: _buildDividendCurve(u),
        dividendDecay: u.dividendCurveEnabled
          ? Math.max(0, Math.min(100, Number(u.dividendDecay) || 0)) : 0,
      }))
    }
    return ctx
  }

  /** Vrai quand l'écran diffère de ce qui est enregistré pour cette variante. */
  const variantDirty = computed(() => {
    const v = variantInfo.value
    if (!v?.parent) return false
    const enregistre = { set: v.delta?.set || {}, removed: v.delta?.removed || [] }
    const courant = deltaCourant.value || { set: {}, removed: [] }
    return JSON.stringify(_trie(courant)) !== JSON.stringify(_trie(enregistre))
  })

  // Les clés d'un objet JSON n'ont pas d'ordre garanti, et `removed` est une
  // liste dont l'ordre ne porte rien : sans tri, deux deltas identiques
  // paraîtraient différents et l'écran annoncerait des modifications fantômes.
  function _trie(d) {
    return {
      set: Object.fromEntries(Object.entries(d.set || {}).sort()),
      removed: [...(d.removed || [])].sort(),
    }
  }

  async function saveVariant() {
    const v = variantInfo.value
    if (!v?.parent) throw new Error("Aucune déclinaison affichée.")
    const delta = deltaCourant.value
    if (!delta) throw new Error("Aucune déclinaison affichée.")

    const res = await apiFetch(`/api/db/scripts/variants/${v.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || "Enregistrement refusé")
    // On rafraîchit les écarts sans recharger l'écran : recharger écraserait
    // ce que l'utilisateur vient de saisir par ce que le serveur en a compris,
    // et un aller-retour invisible est le meilleur moyen de perdre une saisie.
    variantInfo.value = { ...v, ecarts: data.ecarts || [],
                          delta: data.delta || delta,
                          base: data.base_pricing || v.base }
    return data
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
    // Le corps que l'écran envoie pour SON prix. Exposé pour que la
    // comparaison de variantes s'y adosse plutôt que d'en refaire un —
    // deux voies de construction finiraient par classer des produits
    // que l'écran ne price pas.
    inLifeBody: _inLifeBody,
    currentIndicativeId, productTitle, ensureIndicative,
    currentRfqId, pendingDealPrefill, openedDeal,
    parseScript, runPricing, runGreeks,
    runProfile, runPaths, runProba, runBacktest, runMtf,
    runSolver, runGrid, paramIsPct, fromStoredUnits, runScenarios,
    runInLifePricing, isInLife, loadDividendProfile,
    fundingCurve, runImpliedFunding, impliedFunding,
    buildUserParams: _buildUserParams,
    buildConstats: _buildConstats,
    buildDividendCurve: _buildDividendCurve,
    loadYfOne, loadYfAll, loadStrikeCloses,
    addUnderlying, removeUnderlying,
    resetToDefaults, loadFromDb, loadVariant, saveVariant, variantInfo,
    relacherVariante,
    variantDirty,
    loadFromDeal, loadFromRfq, saveScript, updateScript,
    pricingBody: () => ({ ..._baseBody(), N: globalParams.N, antithetic: globalParams.antithetic, ..._rateParams() }),
  }
})
