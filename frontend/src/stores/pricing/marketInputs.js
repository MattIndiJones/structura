// Sous-jacents, paramètres globaux, courbes de taux et de funding, sélection des Greeks.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { anchorDefaultHestonVariance, defaultUnderlying } from '../../utils/underlyingDefaults.js'
import { classifyUnderlying, makeSurface, resizeSurfaceLevel } from '../../utils/volSurface.js'
import { computed, reactive, ref, watch } from 'vue'
import { estimatePricingCalculation } from '../../utils/calculationBudget.js'
import { underlyingGroups } from '../../data/commonUnderlyings.js'
import { _localTodayIso } from './helpers.js'

export function installMarketInputs(s) {
  const {
    script,
  } = s
  // ── Underlyings ───────────────────────────────────────────────────
  const underlyings = ref([defaultUnderlying(1)])
  const corrMatrix = ref([[1.0]])
  // Which underlying is being shown/edited — shared between the Deal tab
  // (ticker picker) and Marché & Paramètres (market-data calibration) so
  // switching the active name in one is reflected in the other.
  const activeUnderlyingIdx = ref(0)

  // ── Global params ─────────────────────────────────────────────────
  const globalParams = reactive({
    r: 3.0,
    T: null,
    N: 20000,
    seed: 42,
    model: 'constant',
    antithetic: true,
    // Terme économique du deal, partagé entre l'onglet Economics et le
    // booking. Il ne rentre pas dans le moteur (qui price en fraction du
    // nominal), mais il doit survivre aux changements d'onglet et aux
    // parcours RFQ / réouverture exactement comme les dates contractuelles.
    nominal: 1_000_000,
    deal_ccy: 'EUR',
    trade_date: new Date().toISOString().split('T')[0],
    strike_date: '',
    value_date: '',
    // Échange final des flux. Vide, le remboursement est actualisé à la
    // maturité — ce qui surestime la note des jours de règlement.
    payment_date: '',
    // Contractual terminal observation. Calendars override it when they carry
    // an explicit last date; otherwise AT MATURITY uses this date and T is
    // derived from strike -> maturity.
    maturity_date: '',
    // Date à laquelle on veut la valeur. Vide ou égale au strike, on price à
    // l'émission ; postérieure, on rejoue le passé et on ne simule que la vie
    // restante. Le mode ne se choisit pas, il se déduit de cette date.
    valuation_date: _localTodayIso(),
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
    barrierMonitoring: 'weekly', stepsPerYear: 52,
  })

  // ── Yield curve (term structure of zero rates) ────────────────────
  watch(() => underlyings.value.map(u => [u, u.ticker, u.sigma, underlyingGroups.length]), (rows, previous = []) => {
    for (const [u,ticker,sigma] of rows) {
      const before=previous.find(row=>row[0]===u)
      const detected=classifyUnderlying(ticker,underlyingGroups)
      if ((u._smileDefaults && u.asset_class==='unknown' && detected!=='unknown') ||
          (before && before[1]!==ticker && detected!=='unknown' && u.vol_surface?.mode==='automatic'
           && u.asset_class!==detected)) {
        u.asset_class=detected
        if (u.vol_level_source==='default') u.sigma=detected==='equity'?30:20
        u.vol_surface=makeSurface(detected,u.sigma,globalParams.T)
        u._smileDefaults=false
      } else if (before && sigma!==before[2] && u.vol_surface && Number(sigma)>0) {
        resizeSurfaceLevel(u)
      }
      anchorDefaultHestonVariance(u)
    }
  }, { flush: 'sync' })

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
    level: 0,              // en %, appliqué à tous les piliers
    pillars: [
      { label: '3M',  T: 0.25, spread: 0 },
      { label: '6M',  T: 0.5,  spread: 0 },
      { label: '1Y',  T: 1.0,  spread: 0 },
      { label: '2Y',  T: 2.0,  spread: 0 },
      { label: '3Y',  T: 3.0,  spread: 0 },
      { label: '5Y',  T: 5.0,  spread: 0 },
      { label: '7Y',  T: 7.0,  spread: 0 },
      { label: '10Y', T: 10.0, spread: 0 },
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
  const _estimateInput = () => ({
    script: script.value,
    maturityYears: globalParams.T,
    underlyings: underlyings.value.length,
    paths: globalParams.N,
    stepsPerYear: globalParams.stepsPerYear,
    model: globalParams.model,
    antithetic: globalParams.antithetic,
    continuousMonitoring: globalParams.barrierMonitoring === 'continuous',
    stochasticRates: globalParams.rateModel !== 'deterministic' && globalParams.sigma_r > 0,
  })
  const pricingEstimate = computed(() => estimatePricingCalculation(_estimateInput()))
  const greeksEstimate = computed(() => estimatePricingCalculation({
    ..._estimateInput(), selectedGreeks: selectedGreeks.value,
  }))

  Object.assign(s, { underlyings, corrMatrix, activeUnderlyingIdx, globalParams, yieldCurve, fundingCurve, _fundingPayload, greekSel, selectedGreeks, _estimateInput, pricingEstimate, greeksEstimate })
}
