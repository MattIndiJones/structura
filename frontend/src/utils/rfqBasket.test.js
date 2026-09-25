import { describe, expect, it } from 'vitest'
import {
  normaliseCorrelation, rfqBasketFromParams, rfqUnderlyingToParams,
} from './rfqBasket.js'

describe('panier RFQ multi-sous-jacents', () => {
  it('ne reconvertit pas les pourcentages d’un panier neuf', () => {
    const [row] = rfqBasketFromParams([], 'EUR')
    expect(row.sigma).toBe(20)
    expect(row.q).toBe(2)
    expect(row.ccy).toBe('EUR')
    expect(rfqUnderlyingToParams(row)).toMatchObject({ sigma: 0.2, q: 0.02 })
  })

  it('arrondit les hypothèses de marché affichées, y compris les modèles de vol', () => {
    const [row] = rfqBasketFromParams([{
      ticker: 'MC.PA', sigma: 0.30099999999999996, q: 0.032799999999999996,
      v0: 0.09060000000000001, rho_h: -0.7000000000000001,
    }])
    expect(row).toMatchObject({ sigma: 30.1, q: 3.28, v0: 9.06, rho_h: -70 })
    const saved = rfqUnderlyingToParams(row)
    expect(saved.v0).toBeCloseTo(0.0906)
    expect(saved.rho_h).toBeCloseTo(-0.7)
  })

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
