import { describe, expect, it } from 'vitest'

import {
  compterConstatations, compterReleves, estReleve, libelleReduction, ordonnerEvenements,
  rangConstatation,
} from './dealEvents.js'

// Ce que le booking crée pour un produit à constatations moyennées : chaque
// constatation d'abord, puis ses relevés — antérieurs à elle en date. Le
// relevé 3/4 est volontairement rangé avant les deux autres.
function evenementsMoyennes() {
  return [
    { id: 10, event_index: 0, event_date: '2026-09-10', parent_event_id: null, label: 'Strike / Fixing S₀' },
    { id: 11, event_index: 1, event_date: '2027-09-10', parent_event_id: null, reduction: 'AVG', label: 'Obs. 1 (1.00Y)' },
    { id: 12, event_index: 2, event_date: '2027-06-10', parent_event_id: 11, label: 'Obs. 1 (1.00Y) · relevé 3/4' },
    { id: 13, event_index: 3, event_date: '2026-12-10', parent_event_id: 11, label: 'Obs. 1 (1.00Y) · relevé 1/4' },
    { id: 14, event_index: 4, event_date: '2027-03-10', parent_event_id: 11, label: 'Obs. 1 (1.00Y) · relevé 2/4' },
    { id: 15, event_index: 5, event_date: '2028-09-11', parent_event_id: null, reduction: 'AVG', label: 'Maturité' },
    { id: 16, event_index: 6, event_date: '2027-12-11', parent_event_id: 15, label: 'Maturité · relevé 1/4' },
  ]
}

describe('les relevés d’un deal booké ne se lisent pas comme des constatations', () => {
  it('annonce les constatations du contrat, pas ses lignes de fixing', () => {
    const evs = evenementsMoyennes()
    expect(compterConstatations(evs)).toBe(3)
    expect(compterReleves(evs)).toBe(4)
  })

  it('place chaque relevé sous sa constatation, dans l’ordre des dates', () => {
    expect(ordonnerEvenements(evenementsMoyennes()).map(e => e.id))
      .toEqual([10, 11, 13, 14, 12, 15, 16])
  })

  it('numérote les constatations sans compter les relevés', () => {
    const evs = evenementsMoyennes()
    // `event_index + 1` aurait affiché 6 : les relevés décalent l'index.
    expect(rangConstatation(evs, evs.find(e => e.id === 15))).toBe(3)
    expect(rangConstatation(evs, evs.find(e => e.id === 13))).toBeNull()
  })

  it('laisse un produit ponctuel exactement tel qu’il s’affichait', () => {
    const evs = [0, 1, 2, 3].map(i => ({
      id: 100 + i, event_index: i, event_date: `202${6 + i}-09-10`, parent_event_id: null,
    }))
    expect(ordonnerEvenements(evs)).toEqual(evs)
    for (const ev of evs) expect(rangConstatation(evs, ev)).toBe(ev.event_index + 1)
  })

  it('lit un événement antérieur au champ comme une constatation', () => {
    // Un deal servi avant l'ajout de `parent_event_id` n'a pas la clé du tout.
    expect(estReleve({ id: 1, event_index: 1 })).toBe(false)
  })

  it('garde visible un relevé dont la constatation est introuvable', () => {
    const evs = [
      { id: 1, event_index: 0, event_date: '2026-09-10', parent_event_id: null },
      { id: 2, event_index: 1, event_date: '2026-12-10', parent_event_id: 99 },
    ]
    expect(ordonnerEvenements(evs).map(e => e.id)).toEqual([1, 2])
  })

  it('dit la règle d’agrégation en français, pas en mot-clé du langage', () => {
    expect(libelleReduction('AVG')).toBe('la moyenne')
    expect(libelleReduction('MIN')).toBe('le plus bas')
    expect(libelleReduction('MAX')).toBe('le plus haut')
    expect(libelleReduction(null)).toBe('')
  })
})
