import { describe, expect, it } from 'vitest'
import {
  normaliseCorrelation, rfqBasketFromParams, rfqUnderlyingToParams,
} from './rfqBasket.js'

describe('panier RFQ multi-sous-jacents', () => {
  it('conserve chaque identité et chaque hypothèse propre au titre', () => {
    const rows = rfqBasketFromParams([
      { name: 'LVMH', ticker: 'MC.PA', ccy: 'EUR', sigma: 0.21, q: 0.018 },
      { name: 'DAX', ticker: '^GDAXI', ccy: 'EUR', sigma: 0.27, q: 0.031,
        heston_v0: 0.07 },
    ])

    expect(rows.map(row => row.ticker)).toEqual(['MC.PA', '^GDAXI'])
    expect(rows[0].sigma).toBeCloseTo(21)
    expect(rows[0].q).toBeCloseTo(1.8)
    expect(rows[1].sigma).toBeCloseTo(27)
    expect(rows[1].q).toBeCloseTo(3.1)
    expect(rfqUnderlyingToParams(rows[1])).toMatchObject({
      name: 'DAX', ticker: '^GDAXI', sigma: 0.27, q: 0.031, heston_v0: 0.07,
    })
  })

  it('agrandit une corrélation existante sans modifier ses paires', () => {
    expect(normaliseCorrelation([[1, 0.42], [0.42, 1]], 3)).toEqual([
      [1, 0.42, 0], [0.42, 1, 0], [0, 0, 1],
    ])
  })
})
