import { watch } from 'vue'

/**
 * La courbe de taux ancrée sur le taux sans risque saisi à l'écran.
 *
 * `r(T) = r + écart × (1 − e^(−T/τ))`
 *
 * Le taux court est le point de départ ; l'écart est la prime de terme totale,
 * atteinte asymptotiquement ; τ dit en combien d'années on en parcourt les
 * deux tiers. La courbe pentifie donc vite sur le court et s'aplatit au long,
 * ce qui est la forme d'une vraie courbe.
 *
 * Une pente ADDITIVE en bps par an aurait été plus simple à écrire et fausse
 * là où ça compte : +25 bps/an donne un 30 ans à 10,5 % sur un taux court à
 * 3 %. Le pilier 30Y n'intéresse personne sur un autocall 3 ans, mais il entre
 * dans l'interpolation et dans le graphe — une courbe qui diverge se voit, et
 * pire, elle se price.
 *
 * L'écart peut être négatif : une courbe inversée s'obtient en le passant sous
 * zéro, sans autre mécanisme.
 */
export function courbeAncree(tauxCourt, ecartBps, tauAnnees, piliers) {
  const r = Number(tauxCourt) || 0
  const ecart = (Number(ecartBps) || 0) / 100        // bps → points de %
  // τ nul ferait une division par zéro et un saut vertical au premier pilier.
  const tau = Math.max(0.05, Number(tauAnnees) || 0)
  return (piliers || []).map(p => ({
    ...p,
    rate: Math.round((r + ecart * (1 - Math.exp(-p.T / tau))) * 1e6) / 1e6,
  }))
}

/**
 * Le lien vivant entre le taux sans risque de l'écran et les piliers.
 *
 * C'est ce que « ancrée sur r » veut dire : modifier le taux court là-haut
 * déplace la courbe ici, sans action supplémentaire.
 *
 * La dérivation ÉCRIT dans les piliers plutôt que de vivre à côté d'eux, et
 * c'est délibéré : tout ce qui part au moteur lit `pillars`. Une courbe dérivée
 * gardée dans un coin se serait affichée sans être pricée — le projet a déjà
 * connu l'hypothèse visible et sans effet.
 *
 * Appelé pendant le setup d'un composant, le watcher est repris par sa portée
 * et s'arrête avec lui.
 */
export function lierAuTauxCourt(courbe, tauxCourt, apresRecalcul = null) {
  return watch(
    () => [courbe.value.ancree, tauxCourt.value, courbe.value.ecart, courbe.value.tau],
    ([ancree]) => {
      if (!ancree) return
      const derivee = courbeAncree(tauxCourt.value, courbe.value.ecart,
                                   courbe.value.tau, courbe.value.pillars)
      derivee.forEach((n, i) => { courbe.value.pillars[i].rate = n.rate })
      if (apresRecalcul) apresRecalcul()
    },
    { immediate: true },
  )
}
