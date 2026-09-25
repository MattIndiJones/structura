import { describe, expect, it } from 'vitest'
import { templateMeta } from '../data/payscriptTemplates.js'
import { productModels } from './productModels.js'
import {
  PAYOFF_FAMILIES, canonicalPayoffFamily, payoffFamilyForModel,
} from './payoffFamilies.js'

describe('classement des payoffs', () => {
  it('regroupe les libellés historiques sans les modifier', () => {
    expect(canonicalPayoffFamily('ATHENA')).toBe('Autocall')
    expect(canonicalPayoffFamily('Autocall')).toBe('Autocall')
    expect(canonicalPayoffFamily('PHOENIX')).toBe('Phoenix')
    expect(canonicalPayoffFamily('Phoenix Memory')).toBe('Phoenix')
    expect(canonicalPayoffFamily('CAPITAL_GUARANTEED')).toBe('Capital protégé')
    expect(canonicalPayoffFamily('Shark')).toBe('Capital protégé')
    expect(canonicalPayoffFamily('REVERSE_CONVERTIBLE')).toBe('Reverse convertible')
    expect(canonicalPayoffFamily('Call')).toBe('Option')
    expect(canonicalPayoffFamily('Swap')).toBe('Échange de flux')
    expect(canonicalPayoffFamily('Produit inconnu')).toBe('')
  })

  it('propose une famille pour chaque modèle et template métier', () => {
    for (const model of productModels) {
      expect(payoffFamilyForModel(model.key), model.key).toBeTruthy()
    }
    for (const template of templateMeta.filter(item => item.group !== 'Validation')) {
      expect(payoffFamilyForModel(template.key), template.key).toBeTruthy()
    }
    expect(PAYOFF_FAMILIES.map(family => family.label)).toEqual([
      'Autocall', 'Phoenix', 'Reverse convertible', 'Capital protégé',
      'Participation', 'Option', 'Crédit lié', 'Échange de flux', 'Autre',
    ])
  })
})
