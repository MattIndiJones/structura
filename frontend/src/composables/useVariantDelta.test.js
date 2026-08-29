/**
 * Le delta d'une déclinaison : ce que l'écran montre, moins l'origine.
 *
 * Deux risques symétriques, et ils ne se valent pas.
 *
 * Un écart MANQUÉ perd une modification à l'enregistrement — l'utilisateur
 * voit son travail disparaître, donc il le refait. Désagréable, mais visible.
 *
 * Un écart FANTÔME est pire : la déclinaison porte une modification que
 * personne n'a saisie, elle price autre chose que ce qui est à l'écran, et
 * l'avertissement « quitter sans enregistrer » se déclenche à chaque
 * navigation — ce qui apprend à cliquer sans lire, et rend l'avertissement
 * inutile le jour où il compte.
 *
 * Ces tests couvrent les deux sens.
 */
import { describe, expect, it } from 'vitest'

import { calculerDelta, contexteDepuisCorps } from './useVariantDelta.js'

const PARENT = {
  script_text: 'PARAM COUPON = 2%\nCONSTAT() OBS\nAT OBS.last:\n  PAY 1\n',
  params: { COUPON: 2, M_KI_BAR: 50 },
  constats: {
    OBS: {
      start_date: '2024-06-14', end_date: '2027-06-14', roll_date: '2024-07-14',
      frequency: { value: 1, unit: 'M' }, stub: 'short_last',
      convention: 'following', settlement_lag: 7,
    },
  },
  global: {
    r: 2.5, T: 3.0, payment_date: '2027-06-23',
    underlyings: [{ name: 'GLE.PA', sigma: 34.27 }, { name: 'STLAM.MI', sigma: 53.15 }],
    corr_matrix: [[1.0, 0.29], [0.29, 1.0]],
  },
}

const DECLARE = { params: ['COUPON', 'M_KI_BAR'], constats: ['OBS'] }

/** Le contexte tel que l'écran le rend après avoir chargé l'origine. */
function ecranNormalise(surcharges = {}) {
  return {
    ...PARENT,
    params: { ...PARENT.params, ...(surcharges.params || {}) },
    constats: {
      OBS: {
        // `_restoreConstats` remplit d'une chaîne vide les champs absents du
        // contexte stocké, et `globalParams` porte ses valeurs par défaut.
        sub_frequency: null,
        ...PARENT.constats.OBS,
        ...(surcharges.obs || {}),
      },
    },
    global: { ...PARENT.global, valuation_date: '', trade_date: '',
              ...(surcharges.global || {}) },
  }
}

describe('aucun écart là où rien n’a été saisi', () => {
  it('une déclinaison qu’on vient d’ouvrir n’a rien de modifié', () => {
    // Sans ça, l'avertissement de sortie se déclencherait à chaque navigation.
    // Trois écarts fantômes apparaissaient ici : un champ absent du contexte
    // stocké et normalisé à '' par l'écran n'est pas une modification, et un
    // décalage de règlement non saisi vaut zéro jour.
    const d = calculerDelta(PARENT, ecranNormalise(), DECLARE)
    expect(d.set).toEqual({})
    expect(d.removed).toEqual([])
  })

  it('ignore les entrées dormantes que le script ne déclare plus', () => {
    // Les surcharges gardent en sommeil les valeurs d'un nom disparu, pour
    // qu'un renommage ne détruise pas une saisie de term sheet. Une entrée
    // dormante n'est pas un terme du produit.
    const avecDormantes = {
      ...ecranNormalise(),
      params: { ...PARENT.params, ANCIEN_PARAM: 9 },
      constats: {
        ...ecranNormalise().constats,
        COUPON_OBS: { start_date: '2024-06-14', end_date: '2027-06-14',
                      frequency: { value: 3, unit: 'M' }, convention: 'none',
                      settlement_lag: 0 },
      },
    }
    expect(calculerDelta(avecDormantes && PARENT, avecDormantes, DECLARE).set).toEqual({})
    // Sans les déclarations, elles remonteraient — c'est le contrôle négatif.
    expect(Object.keys(calculerDelta(PARENT, avecDormantes).set).length).toBeGreaterThan(0)
  })
})

describe('chaque modification réelle est capturée', () => {
  it.each([
    ['un PARAM', { params: { M_KI_BAR: 30 } }, 'params[M_KI_BAR]', 30],
    ['la fin de calendrier', { obs: { end_date: '2029-06-14' } },
      'constats[OBS].end_date', '2029-06-14'],
    ['le décalage de règlement', { obs: { settlement_lag: 3 } },
      'constats[OBS].settlement_lag', 3],
    ['la convention', { obs: { convention: 'modified_following' } },
      'constats[OBS].convention', 'modified_following'],
    ['le règlement final', { global: { payment_date: '2027-07-01' } },
      'global.payment_date', '2027-07-01'],
  ])('%s', (_nom, surcharge, chemin, attendu) => {
    const d = calculerDelta(PARENT, ecranNormalise(surcharge), DECLARE)
    expect(d.set[chemin]).toEqual(attendu)
  })

  it('le texte du payoff', () => {
    const modifie = { ...ecranNormalise(), script_text: `${PARENT.script_text}  PAY 0\n` }
    expect(calculerDelta(PARENT, modifie, DECLARE).set.script).toContain('PAY 0')
  })
})

describe('le panier', () => {
  it('un titre retiré se dit comme un retrait', () => {
    const sansStlam = ecranNormalise()
    sansStlam.global = { ...sansStlam.global, underlyings: [{ name: 'GLE.PA', sigma: 34.27 }] }
    const d = calculerDelta(PARENT, sansStlam, DECLARE)
    expect(d.removed).toEqual(['underlyings[STLAM.MI]'])
  })

  it('un titre ajouté emporte sa définition ET ses corrélations', () => {
    // Même celles que l'écran a remplies par zéro : sur un worst-of une
    // corrélation nulle n'est pas neutre, et la porter explicitement la rend
    // visible dans le panneau des écarts au lieu de la laisser agir en silence.
    const avecSan = ecranNormalise()
    avecSan.global = {
      ...avecSan.global,
      underlyings: [...PARENT.global.underlyings, { name: 'SAN.PA', sigma: 28.0 }],
      corr_matrix: [[1.0, 0.29, 0.62], [0.29, 1.0, 0.0], [0.62, 0.0, 1.0]],
    }
    const ajout = calculerDelta(PARENT, avecSan, DECLARE).set['underlyings[SAN.PA]']
    expect(ajout.sigma).toBe(28.0)
    expect(ajout.correlations).toEqual({ 'GLE.PA': 0.62, 'STLAM.MI': 0.0 })
  })

  it('la calibration d’un titre hérité n’est jamais un écart', () => {
    // C'est une hypothèse de MARCHÉ, commune à toute la famille : la changer
    // ferait mesurer à l'écart de prix un changement d'hypothèse au lieu de la
    // restructuration. Le serveur la refuse aussi.
    const volChangee = ecranNormalise()
    volChangee.global = {
      ...volChangee.global,
      underlyings: [{ name: 'GLE.PA', sigma: 99.0 }, { name: 'STLAM.MI', sigma: 53.15 }],
    }
    expect(calculerDelta(PARENT, volChangee, DECLARE).set).toEqual({})
  })
})

describe('la forme stockée', () => {
  it('se relit depuis le corps de sauvegarde', () => {
    const corps = {
      script_text: 'x',
      params_json: '{"A": 1}',
      constats_json: '{"OBS": {"end_date": "2027-06-14"}}',
      global_params_json: '{"r": 2.5}',
    }
    expect(contexteDepuisCorps(corps)).toEqual({
      script_text: 'x', params: { A: 1 },
      constats: { OBS: { end_date: '2027-06-14' } }, global: { r: 2.5 },
    })
  })
})
