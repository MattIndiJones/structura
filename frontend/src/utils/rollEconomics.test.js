import { describe, expect, it } from 'vitest'
import { comparisonRows, defaultRollFinancing, rollFinancingForm, rollFinancingPayload } from './rollEconomics.js'

describe('hypothèses économiques du roll', () => {
  it('transmet les coûts en points et sépare les champs de bid inactifs', () => {
    const form = { ...defaultRollFinancing(), exit_basis: 'model_haircut', haircut_points: 2,
      exit_cost_points: .5, entry_cost_points: 1, bid_pct: 80, bid_source: 'Old quote' }
    expect(rollFinancingPayload(form)).toEqual({ exit_basis: 'model_haircut', haircut_points: 2,
      exit_cost_points: .5, entry_cost_points: 1 })
  })

  it('convertit une heure locale en instant explicite avec fuseau', () => {
    const date = '2026-06-14T10:30:12.123'
    const payload = rollFinancingPayload({ ...defaultRollFinancing(), exit_basis: 'observed_bid',
      bid_pct: 90, bid_source: ' Bank quotation ', bid_observed_at: date })
    expect(payload.bid_observed_at).toBe(new Date(date).toISOString())
    expect(payload.bid_source).toBe('Bank quotation')
    expect(payload.bid_pct).toBe(90)
  })

  it('préserve l’instant du bid à la réouverture d’une archive', () => {
    const original = { ...defaultRollFinancing(), exit_basis: 'observed_bid', bid_pct: 90,
      bid_source: 'Bank', bid_observed_at: '2026-06-14T10:30:12.123+02:00' }
    const form = rollFinancingForm(original)
    expect(rollFinancingPayload(form).bid_observed_at).toBe('2026-06-14T08:30:12.123Z')
    expect(original.bid_observed_at).toBe('2026-06-14T10:30:12.123+02:00')
  })

  it('normalise les champs inactifs de l’archive sans inventer une saisie', () => {
    expect(rollFinancingForm({ bid_pct: null, bid_observed_at: null })).toEqual(defaultRollFinancing())
  })

  it('ne remplace pas les champs effacés par des coûts ou un bid nuls', () => {
    const payload = rollFinancingPayload({ ...defaultRollFinancing(), exit_basis: 'observed_bid',
      bid_pct: '', exit_cost_points: '', entry_cost_points: '', bid_observed_at: '' })
    expect(payload.bid_pct).toBeNull()
    expect(payload.exit_cost_points).toBeNull()
    expect(payload.entry_cost_points).toBeNull()
    expect(payload.bid_observed_at).toBeNull()
  })

  it('explique un horodatage invalide avant l’envoi', () => {
    expect(() => rollFinancingPayload({ ...defaultRollFinancing(), exit_basis: 'observed_bid',
      bid_observed_at: 'invalid' })).toThrow('Horodatage du bid invalide')
  })

  it('retire l’ancien faux plafond à l’affichage sans modifier l’archive', () => {
    const original = { lignes: [{ mode: 'roll', prix: .9, plafond: .956635, proba_pair_origine: 1 }] }
    const bytes = JSON.stringify(original)
    const rows = comparisonRows(original)
    expect(rows[0].plafond).toBeNull()
    expect(rows[0].reinvested_notional).toBeNull()
    expect(rows[0].recovery_cap_method).toBe('LEGACY_UNQUALIFIED')
    expect(rows[0].proba_pair_origine).toBe(1)
    expect(JSON.stringify(original)).toBe(bytes)
  })

  it('conserve séparément quantité, récupération et plafond des résultats qualifiés', () => {
    const result = { comparison_schema_version: 2, lignes: [{ reinvested_notional: .956635,
      recovery_mean: 1.147961, plafond: 1.147961 }] }
    expect(comparisonRows(result)).toEqual(result.lignes)
    expect(comparisonRows(null)).toEqual([])
  })
})
