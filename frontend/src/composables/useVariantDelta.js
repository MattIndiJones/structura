/**
 * Calcule le delta d'une déclinaison : ce que l'écran montre, moins l'origine.
 *
 * Une variante ne stocke que ses écarts. Pour l'enregistrer il faut donc les
 * DÉDUIRE, en comparant l'état courant au contexte du parent — et le faire sur
 * la forme STOCKÉE, celle que `_scriptBody()` produit déjà, plutôt que sur la
 * forme de requête. Deux raisons : c'est la forme dans laquelle le delta est
 * relu, et c'est la seule sérialisation dont on soit sûr qu'elle décrit le
 * produit en entier.
 *
 * ── Ce qui compte comme un écart, et ce qui n'en est pas un ──
 *
 * Un delta capture des **termes de produit**, pas des réglages de calcul. Le
 * payoff, les PARAM, le calendrier, les dates et la composition du panier en
 * sont ; le nombre de chemins, la graine, le modèle de diffusion, le taux, le
 * funding et les courbes n'en sont pas.
 *
 * Ce n'est pas une simplification : c'est ce qui donne son sens à la
 * comparaison. Toutes les déclinaisons doivent être valorisées sur la MÊME base
 * de marché, sinon l'écart de prix mesure un changement d'hypothèse plutôt que
 * la restructuration. Tester une autre courbe de taux est un scénario, pas une
 * variante — et l'onglet Scénarios est là pour ça.
 */

// Les clés de `global` qui décrivent le produit ET qu'un avenant peut amender.
// Le reste est de l'hypothèse de marché ou du réglage numérique, commun à toute
// la famille.
//
// Absentes délibérément : `strike_date`, `value_date`, `trade_date` et
// `valuation_date`. Les trois premières portent le PASSÉ — le rejeu s'appuie
// dessus, et les déplacer donnerait un prix qui ne décrit plus le produit émis,
// sans que rien ne le signale. La quatrième n'est pas un terme du produit : la
// changer est une re-valorisation, et ferait comparer des déclinaisons à des
// dates différentes. Le serveur les refuse aussi (`_exiger_globale_amendable`) ;
// les exclure ici évite de les capturer pour se les faire refuser ensuite.
//
// La maturité reste amendable, mais par la fin de calendrier
// (`constats[NOM].end_date`), qui est l'endroit où elle se saisit.
const GLOBALES_PRODUIT = ['payment_date', 'T']

// Les champs de CONSTAT qui définissent l'échéancier.
const CHAMPS_CONSTAT = [
  'start_date', 'end_date', 'roll_date', 'frequency', 'sub_frequency',
  'stub', 'convention', 'settlement_lag',
]

// Les champs numériques dont l'absence VAUT zéro. Un décalage de règlement non
// saisi et un décalage de zéro jour ouvré sont le même terme.
const ZERO_VAUT_ABSENT = new Set(['settlement_lag'])

/**
 * Un terme non renseigné, sous ses formes équivalentes.
 *
 * L'écran normalise ce qu'il charge : `_restoreConstats` remplace un champ
 * absent par `''`, et `globalParams` porte ses valeurs par défaut. Le contexte
 * stocké, lui, omet simplement la clé. Comparer les deux littéralement faisait
 * apparaître des écarts qui n'existent pas — trois dès la simple ouverture
 * d'une déclinaison sur un calendrier ordinaire.
 *
 * Ce n'est pas un détail d'affichage : l'état « modifié » commande
 * l'avertissement de sortie. Un avertissement qui se déclenche à chaque
 * navigation apprend à cliquer sans lire, et ne protège plus rien le jour où il
 * compte vraiment.
 */
function estVide(v, champ) {
  if (v === undefined || v === null || v === '') return true
  return v === 0 && ZERO_VAUT_ABSENT.has(champ)
}

/** Deux valeurs sont-elles le même terme ? Tolérance sur les flottants. */
function identique(a, b, champ) {
  if (estVide(a, champ) && estVide(b, champ)) return true
  if (a === b) return true
  if (a == null && b == null) return true
  if (typeof a === 'number' && typeof b === 'number') {
    return Math.abs(a - b) < 1e-9
  }
  if (typeof a === 'object' && typeof b === 'object' && a && b) {
    return JSON.stringify(a) === JSON.stringify(b)
  }
  return false
}

/** Les entrées dont le nom est encore DÉCLARÉ par le script. */
function declarees(surcharges, noms) {
  if (!noms) return surcharges || {}
  const vus = new Set(noms)
  return Object.fromEntries(
    Object.entries(surcharges || {}).filter(([nom]) => vus.has(nom)))
}

/**
 * @param {object} parent   contexte stocké de l'origine {script_text, params, constats, global}
 * @param {object} courant  même forme, produite depuis l'écran
 * @param {object} [declare] {params: [noms], constats: [noms]} — ce que le
 *   script déclare AUJOURD'HUI. Les surcharges gardent en effet dormantes les
 *   valeurs des noms disparus, pour qu'un renommage ou une frappe malheureuse
 *   ne détruise pas une saisie de term sheet. Une entrée dormante n'est pas un
 *   terme du produit : la comparer à l'origine ferait apparaître une
 *   modification que personne n'a saisie.
 * @returns {{set: object, removed: string[]}}
 */
export function calculerDelta(parent, courant, declare = null) {
  const set = {}
  const removed = []
  const p = parent || {}
  const c = {
    ...(courant || {}),
    params: declarees((courant || {}).params, declare?.params),
    constats: declarees((courant || {}).constats, declare?.constats),
  }

  if ((c.script_text || '') !== (p.script_text || '')) {
    set['script'] = c.script_text || ''
  }

  // PARAM : un nom absent de l'écran a disparu du script, il ne se « retire »
  // pas — c'est le script qui a changé, et l'écart est déjà porté par lui.
  for (const [nom, v] of Object.entries(c.params || {})) {
    if (!identique(v, (p.params || {})[nom])) set[`params[${nom}]`] = v
  }

  for (const [nom, valeurs] of Object.entries(c.constats || {})) {
    const ref = (p.constats || {})[nom]
    if (typeof valeurs === 'string') {
      if (valeurs !== ref) set[`constats[${nom}]`] = valeurs
      continue
    }
    for (const champ of CHAMPS_CONSTAT) {
      const avant = ref && typeof ref === 'object' ? ref[champ] : undefined
      if (!identique(valeurs[champ], avant, champ)) {
        set[`constats[${nom}].${champ}`] = valeurs[champ]
      }
    }
  }

  const gc = c.global || {}
  const gp = p.global || {}
  for (const cle of GLOBALES_PRODUIT) {
    if (!identique(gc[cle], gp[cle], cle)) {
      set[`global.${cle}`] = gc[cle]
    }
  }

  // ── Le panier ────────────────────────────────────────────────────
  //
  // Deux écarts, et deux seulement. Un titre RETIRÉ — le seul que la forme
  // delta sait exprimer et qu'une copie perdrait. Un titre AJOUTÉ, avec sa
  // définition entière : il n'a aucun parent dont hériter sa calibration.
  //
  // Ce qui n'est PAS un écart : la calibration d'un titre hérité. C'est une
  // hypothèse de marché, commune à toute la famille, et la changer ferait
  // mesurer à l'écart de prix un changement d'hypothèse au lieu de la
  // restructuration. Le serveur le refuse aussi.
  const ancien = new Map((gp.underlyings || []).map(u => [u.name, u]))
  const courants = gc.underlyings || []
  const nomsCourants = new Set(courants.map(u => u.name))

  for (const u of gp.underlyings || []) {
    if (!nomsCourants.has(u.name)) removed.push(`underlyings[${u.name}]`)
  }

  const survivants = (gp.underlyings || [])
    .map(u => u.name).filter(n => nomsCourants.has(n))
  for (const u of courants) {
    if (ancien.has(u.name)) continue
    // Les corrélations partent EXPLICITEMENT, même celles que l'écran a
    // remplies par zéro. Sur un worst-of une corrélation nulle n'est pas
    // neutre : la porter dans le delta la rend visible dans le panneau des
    // écarts, au lieu de la laisser agir sans que personne l'ait vue.
    set[`underlyings[${u.name}]`] = { ...u, correlations: _correlations(u, gc, survivants) }
  }

  return { set, removed }
}

/** Les corrélations d'un titre ajouté avec ceux qui restent, lues à l'écran. */
function _correlations(u, gc, survivants) {
  const noms = (gc.underlyings || []).map(x => x.name)
  const i = noms.indexOf(u.name)
  const m = gc.corr_matrix || []
  const out = {}
  for (const n of survivants) {
    const j = noms.indexOf(n)
    const v = (i >= 0 && j >= 0) ? m[i]?.[j] : undefined
    out[n] = typeof v === 'number' ? v : 0
  }
  return out
}


/** Le contexte courant, dans la forme STOCKÉE, depuis le corps de sauvegarde. */
export function contexteDepuisCorps(corps) {
  return {
    script_text: corps.script_text || '',
    params: JSON.parse(corps.params_json || '{}'),
    constats: JSON.parse(corps.constats_json || '{}'),
    global: JSON.parse(corps.global_params_json || '{}'),
  }
}
