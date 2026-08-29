import { getCurrentInstance, onBeforeMount, reactive, watch } from 'vue'
import { courbeDividende } from './useDividendCurve.js'

/**
 * Les hypothèses de marché d'un écran : courbe de taux, spread émetteur,
 * courbe de dividende.
 *
 * Une fabrique plutôt qu'un store : l'appel d'offres a besoin des mêmes trois
 * cartes que le Pricer, mais sur SON état. Les faire lire le store du Pricer
 * aurait fait qu'ajuster un AO déplace le prix du masque de pricing ouvert à
 * côté — et réciproquement, sans que rien ne le signale. Chaque appel rend un
 * jeu indépendant ; la conversion vers le moteur, elle, reste unique.
 *
 * `fiches` décrit le panier tel que l'écran le connaît — au minimum un `name`
 * et le rendement `q` en pourcents.
 */
export function useMarketAssumptions(fiches) {
  // Décochées par défaut, toutes les trois. Un prix modèle d'AO se compare aux
  // réponses des contreparties : y glisser une courbe qu'on n'a pas voulue
  // fausserait la comparaison, et c'est le genre d'hypothèse qui agit sans
  // qu'on l'ait vue.
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
  const fundingCurve = reactive({
    enabled: false, mode: 'flat', level: 1.50,
    pillars: [
      { label: '3M', T: 0.25, spread: 1.50 }, { label: '6M', T: 0.5, spread: 1.50 },
      { label: '1Y', T: 1.0, spread: 1.50 }, { label: '2Y', T: 2.0, spread: 1.50 },
      { label: '3Y', T: 3.0, spread: 1.50 }, { label: '5Y', T: 5.0, spread: 1.50 },
    ],
  })
  /**
   * Le panier, et il doit être STABLE.
   *
   * `DividendCurveCard` écrit `dividendCurveEnabled` et `dividendDecay`
   * directement dans la fiche du sous-jacent — c'est ainsi qu'elle fonctionne
   * dans le Pricer, où les fiches sont celles du store. Un `computed` qui
   * reconstruirait les fiches à chaque lecture avalerait ces écritures :
   * l'interrupteur reviendrait à sa position en se relâchant.
   *
   * Le nom et le rendement viennent de l'écran et sont recopiés en place ; les
   * deux champs de dividende appartiennent à la fiche et survivent.
   */
  const panier = reactive([])

  function synchroniser(source) {
    const liste = source || []
    liste.forEach((f, i) => {
      if (!panier[i]) panier[i] = { dividendCurveEnabled: false, dividendDecay: 10.0 }
      panier[i].name = f.name
      panier[i].q = f.q
    })
    panier.length = liste.length
  }

  // Rien ne doit lire les fiches AVANT LA FIN DU SETUP.
  //
  // `useMarketAssumptions` est appelé en haut du setup de l'écran, mais son
  // getter de fiches lit des `const` déclarés bien plus bas dans le même
  // fichier. Toute lecture à la construction tombe donc dans la zone morte
  // temporelle : ReferenceError, composant tué, page entièrement blanche — et
  // un build parfaitement vert, puisque rien de cela n'existe à la compilation.
  //
  // Deux lectures s'y cachaient. `{ immediate: true }` était la première.
  // `watch` est la seconde, moins visible : il évalue son getter une fois à la
  // création pour tracer ses dépendances, même sans `immediate`. Les deux
  // partent donc au montage, qui court après le setup et avant le premier
  // rendu — le panier est prêt à temps, et l'ordre des déclarations cesse de
  // compter. Hors d'un composant — en test — il n'y a pas de montage à attendre.
  function demarrer() {
    synchroniser(fiches.value)
    watch(fiches, synchroniser, { deep: true })
  }
  if (getCurrentInstance()) onBeforeMount(demarrer)
  else demarrer()

  /**
   * Ce qui part au moteur.
   *
   * Le taux et le funding se posent sur le PRODUIT ; le dividende se porte par
   * SOUS-JACENT — c'est un rendement d'action, pas une hypothèse globale. Les
   * mettre au même niveau les ferait ignorer en silence.
   */
  function hypothesesDeMarche() {
    return {
      yield_curve: yieldCurve.enabled
        ? yieldCurve.pillars.map(p => [p.T, p.rate / 100]) : [],
      funding_curve: fundingCurve.enabled && fundingCurve.mode === 'pillars'
        ? fundingCurve.pillars.map(p => [p.T, p.spread / 100]) : [],
      funding_spread: fundingCurve.enabled && fundingCurve.mode === 'flat'
        ? fundingCurve.level / 100 : 0,
    }
  }

  /**
   * Le volet dividende d'un sous-jacent, pour l'horizon donné.
   *
   * Le serveur REFUSE une courbe dont le premier bucket ne vaut pas `q` — la
   * première année de la courbe est le rendement saisi, pas une valeur libre.
   * La dérivation partant de `q`, la règle est satisfaite par construction :
   * elle ne le resterait pas si quelqu'un fixait ici un premier nœud en dur.
   */
  function dividendeDuSousJacent(indice, T) {
    const fiche = panier[indice]
    if (!fiche?.dividendCurveEnabled) return { dividend_curve: [], dividend_decay: 0 }
    return {
      dividend_curve: courbeDividende(fiche, T).map(n => [n.T, n.rate / 100]),
      dividend_decay: (Number(fiche.dividendDecay) || 0) / 100,
    }
  }

  /**
   * Le chemin du retour — et c'est lui qui compte.
   *
   * Rouvrir un AO doit RETROUVER les hypothèses avec lesquelles il a été
   * pricé. Des cartes qui repartent décochées auraient l'air d'un écran neutre,
   * mais le bouton « Calculer prix modèle » renverrait alors `yield_curve: []`
   * et effacerait la courbe enregistrée — un prix qui change sans que personne
   * n'ait touché à une hypothèse.
   *
   * Les nœuds sont réappariés par MATURITÉ, pas par position : une courbe
   * enregistrée avec un autre jeu de piliers restitue ce qu'elle peut et laisse
   * le reste au défaut, plutôt que de décaler toutes les valeurs d'un cran.
   */
  function depuisParams(params) {
    const p = params || {}
    const nodes = (liste) => new Map((liste || []).map(([T, v]) => [Number(T), v]))

    const yc = nodes(p.yield_curve)
    yieldCurve.enabled = yc.size > 0
    yieldCurve.pillars.forEach(pil => {
      if (yc.has(pil.T)) pil.rate = yc.get(pil.T) * 100
    })

    const fc = nodes(p.funding_curve)
    const spread = Number(p.funding_spread) || 0
    fundingCurve.enabled = fc.size > 0 || spread !== 0
    if (fc.size > 0) {
      fundingCurve.mode = 'pillars'
      fundingCurve.pillars.forEach(pil => {
        if (fc.has(pil.T)) pil.spread = fc.get(pil.T) * 100
      })
    } else if (spread !== 0) {
      fundingCurve.mode = 'flat'
      fundingCurve.level = spread * 100
    }

    // Le dividende se porte par SOUS-JACENT : chaque fiche retrouve le sien.
    panier.forEach((fiche, i) => {
      const ul = (p.underlyings || [])[i] || {}
      fiche.dividendCurveEnabled = (ul.dividend_curve || []).length > 0
      if (fiche.dividendCurveEnabled && ul.dividend_decay != null) {
        fiche.dividendDecay = Number(ul.dividend_decay) * 100
      }
    })
  }

  return {
    yieldCurve, fundingCurve, panier,
    hypothesesDeMarche, dividendeDuSousJacent, depuisParams,
  }
}
