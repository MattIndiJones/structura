import { describe, expect, it } from 'vitest'

import { compareMarketSnapshots, compareMarketSnapshotSeries } from './productCalculations.js'

const base = {
  r: 3,
  model: 'constant',
  funding: { mode: 'flat', level: 1.5 },
  underlyings: [
    { ticker: 'AAPL', sigma: 20, q: 0.8 },
    { ticker: 'MSFT', sigma: 18, q: 0.7 },
  ],
  corrMatrix: [[1, 0.35], [0.35, 1]],
}

describe('comparaison des marchés conservés', () => {
  it('isole les mouvements contre le calcul précédent', () => {
    const current = structuredClone(base)
    current.r = 3.25
    current.underlyings[0].sigma = 22
    current.corrMatrix = [[1, 0.4], [0.4, 1]]

    const rows = compareMarketSnapshots(current, base)

    expect(rows.find(row => row.key === 'rate:flat').delta).toBeCloseTo(0.25)
    expect(rows.find(row => row.key === 'ul:0:sigma').delta).toBeCloseTo(2)
    expect(rows.find(row => row.key === 'corr:0:1').delta).toBeCloseTo(0.05)
    expect(rows.find(row => row.key === 'ul:1:q').changed).toBe(false)
  })

  it('conserve une ligne disparue pour rendre le changement visible', () => {
    const current = structuredClone(base)
    current.funding = { mode: 'pillars', pillars: [{ T: 1, label: '1Y', spread: 1.2 }] }

    const rows = compareMarketSnapshots(current, base)

    expect(rows.find(row => row.key === 'funding:flat')).toMatchObject({
      value: null, previousValue: 1.5, changed: true,
    })
    expect(rows.find(row => row.key === 'funding:1')).toMatchObject({
      value: 1.2, previousValue: null, changed: true,
    })
  })

  it('compare une série de plus de deux calculs dans leur ordre', () => {
    const middle = structuredClone(base)
    middle.r = 3.1
    const current = structuredClone(middle)
    current.r = 3.4
    current.underlyings[1].q = 0.9

    const rows = compareMarketSnapshotSeries([base, middle, current])

    expect(rows.find(row => row.key === 'rate:flat')).toMatchObject({
      values: [3, 3.1, 3.4],
      changed: true,
    })
    expect(rows.find(row => row.key === 'rate:flat').deltas[2]).toBeCloseTo(0.3)
    expect(rows.find(row => row.key === 'ul:1:q').values).toEqual([0.7, 0.7, 0.9])
  })
})
