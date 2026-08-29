/**
 * La courbe de dividende, dérivée du rendement et de sa décroissance.
 *
 * Pratique de desk confirmée : le forward se construit par décroissance du
 * passé, `q_année = q1 × (1 − decay)^(année − 1)`. Les nœuds sont des FINS de
 * bucket — `[1, q1]` vaut q1 sur (0, 1 an] — et le dernier se prolonge.
 *
 * Extraite du store pour que l'écran d'appel d'offres puisse s'en servir avec
 * son propre horizon. Une seconde implémentation aurait divergé sur exactement
 * ce genre de convention : la première qui aurait pris les nœuds pour des
 * débuts de bucket aurait décalé toute la courbe d'un an, sans rien signaler.
 */
export function courbeDividende(u, horizonAnnees) {
  if (!u?.dividendCurveEnabled) return []
  const q1 = Math.max(0, Number(u.q) || 0)
  const decay = Math.max(0, Math.min(100, Number(u.dividendDecay) || 0)) / 100
  const annees = Math.max(1, Math.ceil(Number(horizonAnnees) || 1))
  return Array.from({ length: annees }, (_, index) => ({
    label: `A${index + 1}`,
    T: index + 1,
    rate: q1 * Math.pow(1 - decay, index),
  }))
}
