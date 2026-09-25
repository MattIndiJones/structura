import catalogue from '../../../shared/payoffFamilies.json'

export const PAYOFF_FAMILIES = catalogue.families

const lookupKey = value => String(value || '')
  .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
  .toLocaleLowerCase('fr-FR').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()

const byName = new Map()
const byModel = new Map()
for (const family of PAYOFF_FAMILIES) {
  for (const value of [family.code, family.label, ...family.aliases, ...family.model_keys]) {
    byName.set(lookupKey(value), family)
  }
  for (const key of family.model_keys) byModel.set(key, family)
}

export function canonicalPayoffFamily(value) {
  return byName.get(lookupKey(value))?.label || ''
}

export function payoffFamilyForModel(key) {
  return byModel.get(String(key || ''))?.label || ''
}

export function payoffFamilyForDisplay(value) {
  return canonicalPayoffFamily(value) || String(value || '').trim()
}
