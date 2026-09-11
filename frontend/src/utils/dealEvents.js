// Lecture partagée des événements d'un deal booké (backend `_event_row`) —
// utilisée par l'onglet Events et par la page Booking, pour que « combien de
// constatations » et « quel rang » ne divergent jamais entre les deux écrans.
//
// Un relevé de fenêtre (`parent_event_id` renseigné) n'est pas une
// constatation : il alimente la réduction MIN/MAX/AVG de celle qu'il pointe,
// ne paie rien et ne compte pas dans la numérotation. Il garde en revanche sa
// ligne, puisque c'est de son cours que l'agrégat se calcule.

export function estReleve(ev) {
  return ev?.parent_event_id !== null && ev?.parent_event_id !== undefined
}

/**
 * Les événements, chaque relevé placé sous la constatation qu'il alimente.
 *
 * Le tri par date ne suffit pas : les relevés d'une fenêtre PRÉCÈDENT leur
 * constatation, et un tri chronologique pur les afficherait avant elle, sans
 * qu'on voie à quoi ils se rattachent.
 */
export function ordonnerEvenements(events) {
  const tous = events || []
  const enfants = new Map()
  for (const e of tous) {
    if (!estReleve(e)) continue
    if (!enfants.has(e.parent_event_id)) enfants.set(e.parent_event_id, [])
    enfants.get(e.parent_event_id).push(e)
  }
  const sortie = []
  for (const e of tous) {
    if (estReleve(e)) continue
    sortie.push(e)
    const siens = (enfants.get(e.id) || []).slice()
      .sort((a, b) => (a.event_date || '').localeCompare(b.event_date || ''))
    sortie.push(...siens)
  }
  // Un relevé dont la constatation est introuvable reste affiché, en fin de
  // liste : c'est une ligne de fixing, la faire disparaître de l'écran la
  // soustrairait à la saisie sans que personne ne le voie.
  const places = new Set(sortie.map(e => e.id))
  for (const e of tous) {
    if (!places.has(e.id)) sortie.push(e)
  }
  return sortie
}

export function compterConstatations(events) {
  return (events || []).filter(e => !estReleve(e)).length
}

export function compterReleves(events) {
  return (events || []).filter(estReleve).length
}

/**
 * Rang affiché d'une constatation — sa position parmi les constatations, la
 * constatation initiale comprise (comme `event_index + 1` avant les relevés).
 * `null` pour un relevé : il n'est pas numéroté.
 */
export function rangConstatation(events, ev) {
  if (estReleve(ev)) return null
  const i = (events || []).filter(e => !estReleve(e)).findIndex(e => e.id === ev?.id)
  return i < 0 ? null : i + 1
}

const LIBELLES_REDUCTION = { AVG: 'la moyenne', MIN: 'le plus bas', MAX: 'le plus haut' }

/** « la moyenne », « le plus bas », « le plus haut » — pour une phrase, pas un badge. */
export function libelleReduction(reduction) {
  return LIBELLES_REDUCTION[reduction] || reduction || ''
}
