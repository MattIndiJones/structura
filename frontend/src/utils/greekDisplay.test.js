import { describe, expect, it } from 'vitest'
import { strikeBasedDelta, withIndicativeDeltas } from './greekDisplay.js'

describe('delta rapporté au niveau initial', () => {
  it('convertit le choc de 1 % du spot actuel en choc de 1 % du fixing initial', () => {
    const currentSpotDelta = 1.158
    const currentOverInitial = 6297.79 / 4207.16
    expect(strikeBasedDelta(currentSpotDelta, currentOverInitial)).toBeCloseTo(0.7735, 3)
    expect(currentSpotDelta).toBe(1.158)
  })

  it('coïncide avec le delta courant au fixing initial', () => {
    expect(strikeBasedDelta(0.8, 1)).toBe(0.8)
  })

  it('ne présente aucun chiffre sans niveau initial et spot valides', () => {
    expect(strikeBasedDelta(1.158, undefined)).toBeNull()
    expect(strikeBasedDelta(1.158, 0)).toBeNull()
    expect(strikeBasedDelta(1.158, -1)).toBeNull()
    expect(strikeBasedDelta(NaN, 1.5)).toBeNull()
  })

  it('ajoute chaque delta indicatif après le delta Risk sans modifier les valeurs du moteur', () => {
    const entries = [
      { name: 'delta_1', rawValue: 1.158, displayValue: 1.158 },
      { name: 'delta_2', rawValue: 0.6, displayValue: 0.6 },
      { name: 'vega_1', rawValue: 0.21, displayValue: 0.21 },
    ]
    const displayed = withIndicativeDeltas(entries, [{ name: 'A' }, { name: 'B' }], {
      dated: true, spotRatios: { A: 1.5, B: 0.75 }, preStrike: false,
    })
    expect(displayed.map(row => row.name)).toEqual([
      'delta_1', 'delta_1_strike', 'delta_2', 'delta_2_strike', 'vega_1',
    ])
    expect(displayed[1].displayValue).toBeCloseTo(1.158 / 1.5)
    expect(displayed[3].displayValue).toBeCloseTo(0.6 / 0.75)
    expect(entries[0].rawValue).toBe(1.158)
    expect(entries).toHaveLength(3)
  })

  it('ne crée pas de delta rapporté au strike avant le fixing initial', () => {
    const entries = [{ name: 'delta_1', rawValue: 1.158 }]
    expect(withIndicativeDeltas(entries, [{ name: 'A' }], {
      dated: true, spotRatios: {}, preStrike: true,
    })).toEqual(entries)
    expect(withIndicativeDeltas(entries, [{ name: 'A' }], {
      dated: true, spotRatios: {}, preStrike: false,
    })).toEqual(entries)
    expect(withIndicativeDeltas(entries, [{ name: 'A' }], {})).toEqual(entries)
  })
})
