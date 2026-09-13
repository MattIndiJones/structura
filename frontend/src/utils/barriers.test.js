import { describe, expect, it } from 'vitest'

import { barrierGauges } from './barriers.js'

// Ce que la watchlist renvoie pour l'autocall Athena sur MC.PA au 13/09/2026 :
// worst-of à 67,9 % du strike, rappel à 100 %, protection à 55 %.
function athena() {
  return [
    { name: 'M_AC_BAR', kind: 'autocall', observable: 'WOF', level: 1.0, gap_pts: -32.1 },
    { name: 'M_KI_BAR', kind: 'ki', observable: 'WOF', level: 0.55, gap_pts: 12.9 },
  ]
}

describe('la règle des barrières relit les écarts de la watchlist', () => {
  it('place le curseur au niveau que donnent les écarts, sans rien recalculer', () => {
    const [g] = barrierGauges(athena())
    expect(g.observable).toBe('WOF')
    expect(g.current).toBeCloseTo(67.9, 6)
    // Chaque repère et le curseur tiennent dans la règle.
    for (const pct of [g.currentPct, ...g.marks.map(m => m.pct)]) {
      expect(pct).toBeGreaterThan(0)
      expect(pct).toBeLessThan(100)
    }
    const ki = g.marks.find(m => m.kind === 'ki')
    const ac = g.marks.find(m => m.kind === 'autocall')
    expect(ki.pct).toBeLessThan(g.currentPct)
    expect(g.currentPct).toBeLessThan(ac.pct)
  })

  it('ombre sous la protection et au-dessus du rappel, jusqu’au repère exact', () => {
    const [g] = barrierGauges(athena())
    const ki = g.marks.find(m => m.kind === 'ki')
    const ac = g.marks.find(m => m.kind === 'autocall')
    expect(g.lossZonePct).toBeCloseTo(ki.pct, 9)
    expect(g.gainZonePct).toBeCloseTo(100 - ac.pct, 9)
  })

  it('ne place pas un paramètre neutre : une participation à 90 % n’est pas une barrière', () => {
    expect(barrierGauges([
      { name: 'M_PARTICIPATION', kind: 'neutral', observable: 'WOF', level: 0.9, gap_pts: -4.2 },
    ])).toEqual([])
  })

  it('n’invente pas de position avant le strike', () => {
    // gap_pts null = écart pas encore calculable ; le lire comme 0 poserait
    // le curseur pile sur la barrière d'un produit qui n'a pas démarré.
    expect(barrierGauges([
      { name: 'M_KI_BAR', kind: 'ki', observable: 'WOF', level: 0.6, gap_pts: null },
    ])).toEqual([])
    expect(barrierGauges(undefined)).toEqual([])
  })

  it('trace une règle par observable : un KI continu ne se lit pas sur le worst-of courant', () => {
    const gauges = barrierGauges([
      { name: 'M_AC_BAR', kind: 'autocall', observable: 'WOF', level: 1.0, gap_pts: -12.0 },
      { name: 'M_KI_BAR', kind: 'ki', observable: 'WOF_MIN', level: 0.6, gap_pts: 11.5 },
    ])
    expect(gauges.map(g => g.observable)).toEqual(['WOF', 'WOF_MIN'])
    expect(gauges[0].current).toBeCloseTo(88.0, 6)
    expect(gauges[1].current).toBeCloseTo(71.5, 6)
    expect(gauges[0].lossZonePct).toBeNull()
    expect(gauges[1].gainZonePct).toBeNull()
  })

  it('garde lisibles deux repères proches : le second perd son étiquette, pas sa place', () => {
    const [g] = barrierGauges([
      { name: 'M_AC_BAR', kind: 'autocall', observable: 'WOF', level: 1.0, gap_pts: -30.0 },
      { name: 'M_CPN_BAR', kind: 'autocall', observable: 'WOF', level: 0.98, gap_pts: -28.0 },
      { name: 'M_KI_BAR', kind: 'ki', observable: 'WOF', level: 0.6, gap_pts: 10.0 },
    ])
    expect(g.marks.map(m => [m.name, m.labelled])).toEqual([
      ['M_KI_BAR', true], ['M_CPN_BAR', true], ['M_AC_BAR', false],
    ])
    // La zone favorable part de la barrière haussière la plus basse : le
    // coupon se touche avant le rappel.
    expect(g.gainZonePct).toBeCloseTo(100 - g.marks.find(m => m.name === 'M_CPN_BAR').pct, 9)
  })

  it('garde une règle de largeur non nulle quand tout est au même niveau', () => {
    const [g] = barrierGauges([
      { name: 'M_KI_BAR', kind: 'ki', observable: 'WOF', level: 0.6, gap_pts: 0 },
    ])
    expect(g.hi - g.lo).toBeGreaterThanOrEqual(10)
    expect(g.currentPct).toBeCloseTo(g.marks[0].pct, 9)
  })
})
