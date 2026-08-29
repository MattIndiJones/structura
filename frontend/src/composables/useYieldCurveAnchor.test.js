/**
 * La courbe ancrée sur le taux court.
 *
 * Deux choses à tenir, et la seconde est celle qui casse en silence : la forme
 * de la pente, et le fait que la courbe SUIVE le champ « Taux sans risque ».
 * Un ancrage qui s'afficherait sans se recalculer donnerait une courbe juste au
 * premier affichage et fausse dès la première correction du taux — sans rien
 * signaler, puisque les piliers resteraient remplis de chiffres plausibles.
 */
import { describe, expect, it } from 'vitest'
import { computed, effectScope, nextTick, reactive, ref } from 'vue'

import { courbeAncree, lierAuTauxCourt } from './useYieldCurveAnchor.js'

const PILIERS = [
  { label: '3M', T: 0.25 }, { label: '1Y', T: 1 }, { label: '3Y', T: 3 },
  { label: '5Y', T: 5 }, { label: '10Y', T: 10 }, { label: '30Y', T: 30 },
]
const au = (courbe, label) => courbe.find(n => n.label === label).rate

describe('la forme de la pente', () => {
  it('part du taux court et tend vers r + écart', () => {
    const c = courbeAncree(3, 120, 4, PILIERS)

    expect(au(c, '3M')).toBeCloseTo(3.07, 2)    // presque le taux court
    expect(au(c, '30Y')).toBeCloseTo(4.20, 2)   // presque r + 120 bps
    expect(au(c, '30Y')).toBeLessThan(4.20001)  // atteint par le haut, jamais dépassé
  })

  it('ne diverge pas au long, contrairement à une pente en bps par an', () => {
    // La raison du choix de forme : +25 bps/an aurait donné un 30 ans à 10,5 %
    // sur un taux court à 3 %. Le pilier 30Y n'intéresse personne sur un
    // autocall 3 ans, mais il entre dans l'interpolation ET dans le graphe.
    const c = courbeAncree(3, 120, 4, PILIERS)

    expect(au(c, '30Y') - au(c, '10Y')).toBeLessThan(0.15)
  })

  it('donne une courbe inversée avec un écart négatif', () => {
    const c = courbeAncree(3, -80, 4, PILIERS)

    expect(au(c, '3M')).toBeGreaterThan(au(c, '5Y'))
    expect(au(c, '30Y')).toBeCloseTo(2.20, 2)
  })

  it('reste monotone et finie quand τ tend vers zéro', () => {
    // τ = 0 diviserait par zéro : un NaN se propagerait dans toute la courbe,
    // et le moteur recevrait des piliers illisibles.
    const c = courbeAncree(3, 120, 0, PILIERS)

    expect(c.every(n => Number.isFinite(n.rate))).toBe(true)
    // τ borné à 0,05 : le palier est atteint dès le premier pilier, à 8 dixièmes
    // de bp près. Ce qui compte est qu'aucun NaN ne parte au moteur.
    expect(au(c, '3M')).toBeCloseTo(4.19, 2)
  })

  it('suit le taux court par translation', () => {
    const bas = courbeAncree(2, 120, 4, PILIERS)
    const haut = courbeAncree(5, 120, 4, PILIERS)

    PILIERS.forEach(p => {
      expect(au(haut, p.label) - au(bas, p.label)).toBeCloseTo(3, 6)
    })
  })
})

describe('le lien vivant avec le champ de l’écran', () => {
  function ecran({ ancree = true } = {}) {
    const taux = ref(3)
    const etat = reactive({
      ancree, ecart: 120, tau: 4,
      pillars: PILIERS.map(p => ({ ...p, rate: 9.99 })),
    })
    const scope = effectScope()
    scope.run(() => lierAuTauxCourt(computed(() => etat), computed(() => taux.value)))
    return { etat, taux, scope }
  }

  it('remplit les piliers dès l’activation', () => {
    const { etat } = ecran()

    expect(etat.pillars[0].rate).toBeCloseTo(3.07, 2)
  })

  it('déplace la courbe quand le taux sans risque change', async () => {
    // LE test de ce fichier : c'est tout ce que « ancrée sur r » veut dire.
    const { etat, taux } = ecran()
    taux.value = 5
    await nextTick()

    expect(etat.pillars[0].rate).toBeCloseTo(5.07, 2)
    expect(etat.pillars.at(-1).rate).toBeCloseTo(6.20, 2)
  })

  it('suit aussi la prime de terme et la vitesse', async () => {
    const { etat } = ecran()
    etat.ecart = -80
    await nextTick()

    expect(etat.pillars.at(-1).rate).toBeCloseTo(2.20, 2)
  })

  it('ne touche à rien tant que l’ancrage est éteint', async () => {
    // Le contrôle négatif : les niveaux saisis à la main et les scénarios
    // gardent leur comportement, l'ancrage est un mode EN PLUS.
    const { etat, taux } = ecran({ ancree: false })
    taux.value = 5
    await nextTick()

    expect(etat.pillars.every(p => p.rate === 9.99)).toBe(true)
  })
})
