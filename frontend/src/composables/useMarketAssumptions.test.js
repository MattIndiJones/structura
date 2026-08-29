/**
 * Une hypothèse de marché doit ATTEINDRE le moteur, et y RESTER.
 *
 * Le projet a déjà connu des courbes saisissables sans le moindre effet sur le
 * prix — une courbe de dividende à 8 % vaut pourtant −491,6 bps. Un test qui
 * ne vérifie qu'une valeur ne voit pas un fil débranché ; ceux-ci vérifient le
 * PAYLOAD, et surtout le retour : rouvrir un AO doit retrouver ce avec quoi il
 * a été pricé, faute de quoi le prochain « Calculer prix modèle » l'efface.
 */
import { describe, expect, it } from 'vitest'
import { computed, createRenderer, defineComponent, h, nextTick, ref } from 'vue'

import { useMarketAssumptions } from './useMarketAssumptions.js'

/** Un écran mono-sous-jacent, comme l'appel d'offres. */
function ecran(q = 4) {
  const fiches = ref([{ name: 'STM', q }])
  return { ...useMarketAssumptions(computed(() => fiches.value)), fiches }
}

describe('les hypothèses partent au moteur', () => {
  it('ne transmet rien tant que rien n’est coché', () => {
    // Le contrôle négatif. Un prix modèle d'AO se compare aux réponses des
    // contreparties : une courbe qu'on n'a pas voulue fausserait la comparaison.
    const { hypothesesDeMarche, dividendeDuSousJacent } = ecran()

    expect(hypothesesDeMarche()).toEqual({
      yield_curve: [], funding_curve: [], funding_spread: 0,
    })
    expect(dividendeDuSousJacent(0, 3)).toEqual({
      dividend_curve: [], dividend_decay: 0,
    })
  })

  it('transmet la courbe de taux en décimal une fois cochée', () => {
    const { yieldCurve, hypothesesDeMarche } = ecran()
    yieldCurve.enabled = true
    yieldCurve.pillars.find(p => p.T === 1).rate = 5.0

    const envoye = hypothesesDeMarche().yield_curve
    expect(envoye).toHaveLength(11)   // les mêmes piliers que le Pricer, 3M → 30Y
    expect(envoye).toContainEqual([1, 0.05])
  })

  it('sépare le spread plat de la courbe par pilier', () => {
    // Les deux modes ne se cumulent pas : le moteur lit `funding_spread` OU
    // `funding_curve`. Les envoyer ensemble compterait le crédit deux fois.
    const { fundingCurve, hypothesesDeMarche } = ecran()
    fundingCurve.enabled = true
    fundingCurve.level = 1.5

    expect(hypothesesDeMarche()).toMatchObject({ funding_spread: 0.015, funding_curve: [] })

    fundingCurve.mode = 'pillars'
    const enMode = hypothesesDeMarche()
    expect(enMode.funding_spread).toBe(0)
    expect(enMode.funding_curve).toHaveLength(6)
  })

  it('fait décroître le dividende depuis q, sur l’horizon demandé', () => {
    // Les deux réglages vivent DANS la fiche : c'est là que la carte les écrit.
    const { panier, dividendeDuSousJacent } = ecran(4)
    panier[0].dividendCurveEnabled = true
    panier[0].dividendDecay = 10

    const { dividend_curve, dividend_decay } = dividendeDuSousJacent(0, 3)
    expect(dividend_decay).toBe(0.1)
    expect(dividend_curve).toHaveLength(3)
    expect(dividend_curve[1][1]).toBeCloseTo(0.036, 10)   // 4 % × 0,9
  })

  it('pose toujours q en premier bucket — le serveur refuse le contraire', async () => {
    // Le premier bucket EST le rendement saisi, pas une valeur libre : une
    // courbe qui démarre ailleurs part en 422. La dérivation partant de q, la
    // règle tient par construction — ce test la tient quand elle changera.
    const { panier, fiches, dividendeDuSousJacent } = ecran(4)
    panier[0].dividendCurveEnabled = true
    fiches.value = [{ name: 'STM', q: 6.25 }]
    await nextTick()

    expect(dividendeDuSousJacent(0, 3).dividend_curve[0]).toEqual([1, 0.0625])
  })
})

describe('rouvrir un AO retrouve ses hypothèses', () => {
  it('fait l’aller-retour sans rien perdre', () => {
    // LE test de ce fichier. Sans lui, les cartes rouvriraient décochées et le
    // bouton renverrait `yield_curve: []` — un prix qui change alors que
    // personne n'a touché à une hypothèse.
    const source = ecran(4)
    source.yieldCurve.enabled = true
    source.yieldCurve.pillars.find(p => p.T === 2).rate = 4.4
    source.fundingCurve.enabled = true
    source.fundingCurve.level = 2.25
    source.panier[0].dividendCurveEnabled = true
    source.panier[0].dividendDecay = 15

    const enregistre = {
      ...source.hypothesesDeMarche(),
      underlyings: [{ ...source.dividendeDuSousJacent(0, 3) }],
    }

    const relu = ecran(4)
    relu.depuisParams(enregistre)

    expect({
      ...relu.hypothesesDeMarche(),
      underlyings: [{ ...relu.dividendeDuSousJacent(0, 3) }],
    }).toEqual(enregistre)
  })

  it('réapparie les nœuds par maturité, pas par position', () => {
    // Une courbe enregistrée avec d'autres piliers restitue ce qu'elle peut et
    // laisse le reste au défaut. Un appariement par index aurait décalé toutes
    // les valeurs d'un cran, sans rien signaler.
    const { yieldCurve, depuisParams } = ecran()
    depuisParams({ yield_curve: [[2, 0.044], [5, 0.048]] })

    expect(yieldCurve.enabled).toBe(true)
    expect(yieldCurve.pillars.find(p => p.T === 2).rate).toBeCloseTo(4.4, 10)
    expect(yieldCurve.pillars.find(p => p.T === 5).rate).toBeCloseTo(4.8, 10)
    expect(yieldCurve.pillars.find(p => p.T === 1).rate).toBe(3.6)   // défaut intact
  })

  it('rouvre décoché un AO pricé sans hypothèse', () => {
    const { yieldCurve, fundingCurve, panier, depuisParams } = ecran()
    depuisParams({ yield_curve: [], funding_curve: [], funding_spread: 0, underlyings: [{}] })

    expect(yieldCurve.enabled).toBe(false)
    expect(fundingCurve.enabled).toBe(false)
    expect(panier[0].dividendCurveEnabled).toBe(false)
  })

  it('supporte un AO enregistré avant que les cartes existent', () => {
    // `params` d'alors ne portait aucune de ces clés. Rien ne doit lever.
    const { yieldCurve, fundingCurve, panier, depuisParams } = ecran()
    depuisParams({ r: 0.03, N: 20000, model: 'constant' })

    expect(yieldCurve.enabled).toBe(false)
    expect(fundingCurve.enabled).toBe(false)
    expect(panier[0].dividendCurveEnabled).toBe(false)
  })
})

describe('deux écrans ne se marchent pas dessus', () => {
  it('garde chaque jeu indépendant', () => {
    // La raison d'être de la fabrique : ajuster un AO ne doit pas déplacer le
    // prix du masque ouvert à côté, ni l'inverse.
    const creation = ecran()
    const detail = ecran()

    detail.yieldCurve.enabled = true
    detail.yieldCurve.pillars[0].rate = 9.9

    expect(creation.yieldCurve.enabled).toBe(false)
    expect(creation.yieldCurve.pillars[0].rate).toBe(3.2)
  })
})


describe('la carte de dividende écrit dans une fiche qui dure', () => {
  it('ne perd pas le réglage quand le sous-jacent change de nom ou de q', async () => {
    // `DividendCurveCard` écrit `dividendCurveEnabled` et `dividendDecay`
    // DIRECTEMENT dans la fiche. Un panier reconstruit à chaque lecture
    // avalait ces écritures : l'interrupteur revenait en se relâchant.
    const { panier, fiches } = ecran(4)
    panier[0].dividendCurveEnabled = true
    panier[0].dividendDecay = 15

    fiches.value = [{ name: 'STM', q: 5 }]   // l'écran change le rendement
    await nextTick()

    expect(panier[0].q).toBe(5)
    expect(panier[0].dividendCurveEnabled).toBe(true)
    expect(panier[0].dividendDecay).toBe(15)
  })
})

/**
 * La page blanche.
 *
 * `useMarketAssumptions` est appelé en haut du setup de l'écran, mais son
 * getter de fiches lit des `const` déclarés bien plus bas dans le même fichier.
 * Une première synchronisation exécutée à la CONSTRUCTION tombait donc dans la
 * zone morte temporelle : ReferenceError, composant tué, écran entièrement
 * vide — et un `npm run build` parfaitement vert, puisque rien de tout cela
 * n'est visible à la compilation.
 *
 * Ce test monte pour de bon. Un test qui n'aurait vérifié que la valeur du
 * panier serait resté vert pendant que la page ne s'affichait plus.
 */
describe('l’écran se monte quel que soit l’ordre des déclarations', () => {
  /**
   * Un montage CLIENT, sans DOM : un renderer minimal suffit à obtenir les
   * vrais cycles de vie. Le rendu SSR ne convenait pas — il saute
   * `onBeforeMount`, donc il aurait décrit un chemin que l'application
   * n'emprunte jamais.
   */
  function monter(composant) {
    const noeud = () => ({ enfants: [], texte: '' })
    const { createApp } = createRenderer({
      createElement: noeud,
      createText: (t) => ({ ...noeud(), texte: t }),
      setText: (n, t) => { n.texte = t },
      setElementText: (n, t) => { n.texte = t },
      insert: (enfant, parent) => { parent.enfants.push(enfant) },
      remove: () => {},
      patchProp: () => {},
      parentNode: () => null,
      nextSibling: () => null,
    })
    const racine = noeud()
    createApp(composant).mount(racine)
    return racine
  }

  it('ne lit pas les fiches avant la fin du setup', () => {
    // La page blanche venait de là, et de rien d'autre : un ReferenceError de
    // zone morte tue le composant sans laisser la moindre trace à la
    // compilation. Le `npm run build` était vert.
    const Ecran = defineComponent({
      setup() {
        // Exactement la structure de RfqView : la fabrique d'abord…
        const m = useMarketAssumptions(computed(() => [{ name: 'STM', q: tardif.q }]))
        // …la dépendance ensuite, donc en zone morte pendant le setup.
        const tardif = { q: 4 }
        return () => h('span', String(m.panier.length))
      },
    })

    expect(() => monter(Ecran)).not.toThrow()
  })

  it('a son panier prêt avant le premier rendu', () => {
    // Le second piège, plus discret : différer la synchronisation trop loin
    // rendrait un panier vide au premier passage — la carte de dividende
    // n'aurait rien à afficher, sans erreur ni symptôme.
    const vus = []
    const Ecran = defineComponent({
      setup() {
        const m = useMarketAssumptions(computed(() => [{ name: 'STM', q: tardif.q }]))
        const tardif = { q: 4 }
        return () => {
          vus.push(m.panier.map(f => f.q))
          return h('span', 'ok')
        }
      },
    })
    monter(Ecran)

    expect(vus[0]).toEqual([4])
  })
})
