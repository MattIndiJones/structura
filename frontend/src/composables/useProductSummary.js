/**
 * Résumé écrit d'un produit — payoff, hypothèses, prix, risque.
 *
 * Une seule fonction produit le texte, et TROIS consommateurs le partagent :
 * l'onglet Résumé, le presse-papier, et l'envoi à une IA. Les faire diverger
 * distribuerait un résumé qui décrit un autre produit que le prix affiché.
 *
 * Deux règles qui gouvernent le contenu :
 *
 *  1. Tout vient du SNAPSHOT qui a produit le prix (`result._inputs`), jamais
 *     de l'état courant de l'écran. Sinon un paramètre modifié après le
 *     pricing produirait un résumé décrivant un produit qui n'a jamais été
 *     pricé. La péremption se lit, elle ne se devine pas.
 *
 *  2. Les hypothèses sont données AVEC leur provenance. « σ = 53 % » ne
 *     permet à personne — humain ou modèle — de juger si l'hypothèse est
 *     raisonnable ; « Stellantis, vol réalisée 1 an au 08/05/2026 » oui.
 *
 * Les champs commerciaux (contrepartie, nominal, prix traité, marge) sont
 * masqués par défaut : analyser un payoff n'en a pas besoin, et ce texte est
 * destiné à sortir du desk.
 */

const nb = (v, d = 2) =>
  v == null || Number.isNaN(Number(v))
    ? '—'
    : Number(v).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d })

/** Comme nb(), mais sans traîner de zéros inutiles. */
const nbSouple = v =>
  v == null || Number.isNaN(Number(v))
    ? '—'
    : Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 4 })

const pct = (v, d = 2) => (v == null ? '—' : `${nb(v, d)} %`)

const jour = iso => {
  if (!iso) return '—'
  const [a, m, j] = String(iso).split('-')
  return j ? `${j}/${m}/${a}` : iso
}

/** Les paramètres du script, dans les unités que l'écran affiche. */
function ligneParams(inputs) {
  return (inputs.paramsUsed || [])
    // Décimales utiles seulement : un seuil rond s'écrit « 100 % », pas
    // « 100,0000 % ». Le coupon mensuel, lui, en a besoin de quatre.
    .map(p => `${p.name} = ${nbSouple(p.value)}${p.is_pct ? ' %' : ''}`)
    .join(' · ')
}

/** Le calendrier de constatation, décrit en une phrase par CONSTAT. */
function lignesCalendrier(inputs) {
  const CONV = {
    none: 'aucun ajustement', following: 'jour ouvré suivant',
    modified_following: 'suivant sauf changement de mois',
    preceding: 'jour ouvré précédent',
    modified_preceding: 'précédent sauf changement de mois',
  }
  return Object.entries(inputs.constats || {})
    .filter(([, v]) => v && typeof v === 'object' && v.start_date)
    .map(([nom, v]) => {
      const freq = v.frequency ? `${v.frequency.value}${v.frequency.unit}` : '—'
      const lag = Number(v.settlement_lag) || 0
      return `- ${nom} : du ${jour(v.start_date)} au ${jour(v.end_date)}, tous les ${freq}`
        + `, ${CONV[v.convention] || v.convention || 'aucun ajustement'}`
        + `, règlement ${lag ? `J+${lag} ouvrés` : 'le jour même'}`
    })
}

/** Sous-jacents et leur calibration, avec ce qui l'a produite. */
function lignesSousJacents(inputs, result) {
  const niveaux = result?.past?.strike_levels || {}
  const perfs = result?.past?.performances || {}
  return (inputs.underlyings || []).map(u => {
    const bouts = [`σ ${pct(u.sigma)}`, `q ${pct(u.q)}`]
    if (u.dividendCurveEnabled) bouts.push(`dividende dégressif (−${nb(u.dividendDecay, 0)} %/an)`)
    if (niveaux[u.name] != null) bouts.push(`S₀ ${nb(niveaux[u.name], 3)}`)
    if (perfs[u.name] != null) bouts.push(`niveau actuel ${pct(perfs[u.name] * 100, 1)} du strike`)
    return `- ${u.name}${u.ticker && u.ticker !== u.name ? ` (${u.ticker})` : ''} — ${bouts.join(', ')}`
  })
}

function lignesCorrelation(inputs) {
  const m = inputs.corrMatrix || []
  const noms = (inputs.underlyings || []).map(u => u.name)
  const out = []
  for (let i = 0; i < m.length; i++) {
    for (let j = i + 1; j < (m[i] || []).length; j++) {
      out.push(`${noms[i]}/${noms[j]} ${nb(m[i][j], 2)}`)
    }
  }
  return out
}

function lignesMarche(inputs) {
  const L = []
  L.push(`- Taux : ${inputs.yieldCurveEnabled
    ? `courbe (${(inputs.yieldCurvePillars || []).map(p => `${p.label} ${nb(p.rate, 2)} %`).join(', ')})`
    : `plat ${pct(inputs.r)}`}`)
  if (inputs.funding) {
    const f = inputs.funding
    L.push(`- Spread émetteur : ${f.mode === 'pillars'
      ? `par pilier (${f.pillars.map(p => `${p.label} ${nb(p.spread * 100, 0)} bps`).join(', ')})`
      : `${nb(f.level * 100, 0)} bps, plat`} — actualisation seule`)
  } else {
    L.push('- Spread émetteur : aucun (actualisation au taux sans risque)')
  }
  const MODELES = { constant: 'Constant (GBM)', heston: 'Heston', sabr: 'SABR',
                     localvol: 'Dupire (local vol)', lsv: 'Local-stochastic vol' }
  L.push(`- Modèle de diffusion : ${MODELES[inputs.model] || inputs.model}`)
  if (inputs.sigma_r) L.push(`- Taux stochastique : σ_r ${pct(inputs.sigma_r)}, a ${nb(inputs.a_r, 2)}`)
  L.push(`- Monte Carlo : ${nb(inputs.N, 0)} chemins, graine ${inputs.seed}`
    + `${inputs.antithetic ? ', variantes antithétiques' : ''}`
    + `, monitoring de barrière ${inputs.barrierMonitoring === 'continuous' ? 'continu' : 'hebdomadaire'}`)
  return L
}

function lignesRisque(result, inputs) {
  const L = []
  const g = result?.greeks || {}
  const NOMS = { delta: 'Δ', gamma: 'Γ', vega: 'ν', theta: 'Θ', rho: 'ρ', credit: 'CR' }
  const noms = (inputs?.underlyings || []).map(u => u.name)
  const parType = {}
  for (const [cle, val] of Object.entries(g)) {
    if (typeof val !== 'number') continue
    const m = cle.match(/^([a-z]+)(?:_(\d+))?$/)
    if (!m) continue
    // Une sensibilité par sous-jacent DOIT porter son nom : « 0,60 » en
    // troisième position ne dit rien, « Stellantis 0,60 » dit que tout le
    // risque est là. C'est la seule information que le lecteur cherche.
    const etiquette = m[2] ? (noms[Number(m[2]) - 1] || `S${m[2]}`) : null
    ;(parType[m[1]] ||= []).push(etiquette ? `${etiquette} ${nb(val, 4)}` : nb(val, 4))
  }
  for (const [type, vals] of Object.entries(parType)) {
    L.push(`- ${NOMS[type] || type} : ${vals.join(' · ')}`)
  }
  if (result?.fugit != null) L.push(`- Fugit (durée de vie moyenne) : ${nb(result.fugit, 2)} ans`)
  return L
}

/** La distribution des résultats, telle que l'onglet Probabilités l'a mesurée.
 *
 *  Elle vit hors de `result` (un second appel MC, échantillon dédié), donc hors
 *  de l'instantané. Deux conséquences qui se lisent dans le texte plutôt que de
 *  se deviner :
 *
 *   - si elle décrit une AUTRE jambe que le prix (probabilités d'émission sous
 *     un prix de cours de vie, ou l'inverse), on ne l'escamote pas — on le DIT.
 *     L'omettre en silence laissait croire que l'onglet n'avait pas tourné ;
 *     l'inclure sans le dire ferait raisonner sur un produit chimérique.
 *   - si elle n'a pas tourné du tout, on le signale aussi : un lecteur — humain
 *     ou modèle — doit savoir que le silence sur les probabilités est un manque
 *     de mesure, pas une absence de risque.
 */
function lignesProbabilites(proba, result) {
  const enCours = !!result?.in_life
  if (!proba) {
    return ["- Non mesurée — lancez l'onglet Probabilités pour l'obtenir."]
  }

  const L = []
  if (!!proba.in_life !== enCours) {
    L.push(`> ⚠ Ces probabilités ont été mesurées ${proba.in_life
      ? 'sur la vie RESTANTE' : "à l'ÉMISSION"}, alors que le prix ci-dessus est`
      + ` ${enCours ? 'un prix de cours de vie' : "un prix d'émission"}.`
      + ' Elles ne décrivent donc PAS la même jambe que le prix : à relancer'
      + ' avant toute conclusion.')
    L.push('')
  }

  if (proba.has_autocall) {
    L.push('- P(rappel anticipé) : ' + pct(proba.autocall_pct, 1))
    L.push('- P(perte en capital à maturité) : ' + pct(proba.ki_pct, 1))
    if (proba.total > 0) {
      L.push('- P(remboursement sans perte, sans rappel) : '
        + pct(proba.normal_count / proba.total * 100, 1))
    }
    L.push('- Durée espérée : ' + nb(proba.expected_life, 2) + ' ans')
  } else {
    if (proba.total > 0) {
      L.push('- P(dans la monnaie) : ' + pct(proba.normal_count / proba.total * 100, 1))
    }
    L.push('- P(hors de la monnaie) : ' + pct(proba.ki_pct, 1))
  }

  // Deux mesures que le compte de KI ne donne pas : « remboursé sous le pair »
  // couvre aussi les chemins qui perdent sans franchir de barrière, et « coupon
  // plein » dit si le rendement annoncé est réellement atteignable.
  if (proba.capital_loss_pct != null) {
    L.push('- P(remboursement sous le pair) : ' + pct(proba.capital_loss_pct, 1))
  }
  if (proba.full_coupon_pct != null) {
    L.push('- P(payoff maximal atteint) : ' + pct(proba.full_coupon_pct, 1))
  }

  const p = proba.percentiles || {}
  if (p.p5 != null) {
    L.push(`- Percentiles du payoff : P5 ${pct(p.p5, 2)} · P25 ${pct(p.p25, 2)}`
      + ` · P75 ${pct(p.p75, 2)} · P95 ${pct(p.p95, 2)}`)
  }

  // Le profil de rappel dans le temps : c'est lui qui dit si le produit est
  // « rappelé tôt ou jamais » ou « rappelé progressivement » — deux économies
  // très différentes sous une même P(rappel) agrégée.
  const dates = lignesRappelParDate(proba)
  if (dates) L.push(dates)

  if (proba.total) {
    L.push(`- Échantillon : ${Number(proba.total).toLocaleString('fr-FR')} chemins`
      + ' (tirage dédié, distinct de celui du prix)')
  }
  return L
}

/** Les premières dates de rappel, quand elles portent l'essentiel de la masse. */
function lignesRappelParDate(proba) {
  const counts = proba.event_counts || {}
  const total = proba.total || 0
  const items = Object.entries(counts)
    .map(([t, n]) => [Number(t), Number(n)])
    .filter(([t, n]) => Number.isFinite(t) && n > 0)
    .sort((a, b) => a[0] - b[0])
  if (!items.length || !total) return ''
  const parts = items.slice(0, 6)
    .map(([t, n]) => `${nbSouple(t)} → ${pct(n / total * 100, 1)}`)
  const reste = items.length > 6 ? ' · …' : ''
  return `- Rappel par date (années) : ${parts.join(' · ')}${reste}`
}

/**
 * @param {object} store    store de pricing
 * @param {object} options  { commercial: false } — masque par défaut
 * @returns {{ok: boolean, texte: string, perime: boolean, raison?: string}}
 */
export function buildProductSummary(store, options = {}) {
  const result = store.result
  const inputs = result?._inputs
  if (!result || !inputs) {
    return { ok: false, texte: '', perime: false,
             raison: 'Lancez un pricing : le résumé décrit le produit qui a produit le prix.' }
  }

  const enCours = !!result.in_life
  const L = []
  const titre = inputs.scriptName || 'Produit sans nom'

  L.push(`# ${titre}`)
  L.push('')
  L.push(enCours
    ? `Valorisation en cours de vie au ${jour(result.valuation_date)} — `
      + `${nb(result.past.years_elapsed, 2)} an écoulé, ${nb(result.past.years_remaining, 2)} restant.`
    : `Valorisation à l'émission.`)
  L.push('')

  L.push('## Payoff')
  L.push('')
  L.push('Le payoff est décrit en PayScript, le DSL de l\'application. `CONSTAT()` déclare')
  L.push('un calendrier d\'observation, `AT <nom>:` un bloc exécuté à chaque date de ce')
  L.push('calendrier, `AT <nom>.last:` uniquement à la dernière. `WOF` est la performance')
  L.push('du moins bon sous-jacent, `INDIC(x)` vaut 1 si la condition tient, `PAY` verse un')
  L.push('flux, `STOP` termine le produit.')
  L.push('')
  L.push('```')
  L.push((inputs.script || '').trim())
  L.push('```')
  L.push('')
  L.push(`Paramètres : ${ligneParams(inputs) || '—'}`)
  L.push('')

  L.push('## Calendrier')
  L.push('')
  L.push(`- Constatation initiale (strike) : ${jour(inputs.strike_date)}`)
  L.push(`- Date de valeur : ${jour(inputs.value_date)}`)
  L.push(`- Dernière constatation : ${jour(inputs.maturity_date)}`)
  L.push(`- Règlement final : ${jour(inputs.payment_date)}`)
  const cal = lignesCalendrier(inputs)
  if (cal.length) { L.push(''); L.push(...cal) }
  L.push('')

  L.push('## Sous-jacents')
  L.push('')
  L.push(...lignesSousJacents(inputs, result))
  const corr = lignesCorrelation(inputs)
  if (corr.length) { L.push(''); L.push(`Corrélations : ${corr.join(' · ')}`) }
  L.push('')

  L.push('## Hypothèses de marché')
  L.push('')
  L.push(...lignesMarche(inputs))
  if (enCours) {
    L.push('')
    L.push('Les hypothèses ci-dessus sont celles saisies à la date de valorisation.')
  }
  L.push('')

  L.push('## Prix')
  L.push('')
  L.push(`- Prix équitable : ${pct(result.price * 100)} du nominal`)
  if (result.ic95) {
    L.push(`- Intervalle de confiance 95 % : [${pct(result.ic95[0] * 100)}, ${pct(result.ic95[1] * 100)}]`)
  }
  if (enCours) {
    const p = result.past
    if (p.worst_of != null) L.push(`- Worst-of à la valorisation : ${pct(p.worst_of * 100, 1)} du strike`)
    L.push(`- Constatations déjà passées : ${p.observations_done}`)
    const etat = Object.entries(p.memory || {})
    if (etat.length) {
      L.push(`- État repris du passé : ${etat.map(([k, v]) => `${k} ${nb(v, 4)}`).join(' · ')}`)
    }
  }
  const probas = lignesProbabilites(store.proba, result)
  if (probas.length) {
    L.push('')
    L.push('## Distribution des résultats')
    L.push('')
    L.push(...probas)
  }

  const risque = lignesRisque(result, inputs)
  if (risque.length) {
    L.push('')
    L.push('## Risque')
    L.push('')
    L.push(...risque)
    L.push('')
    L.push('Les sensibilités sont exprimées par unité de choc : Δ pour +1 % de spot,')
    L.push('ν pour +1 point de volatilité, ρ et CR pour +100 bps.')
  }

  if (options.commercial) {
    L.push('')
    L.push('## Commercial')
    L.push('')
    L.push(`- Devise de règlement : ${inputs.deal_ccy || '—'}`)
  }

  return { ok: true, texte: L.join('\n'), perime: false }
}
