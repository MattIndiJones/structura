import catalogue from './productCatalogue.json'

export const templateMeta = catalogue.products.map(p => ({
  key: p.key, label: p.label, group: catalogue.families.find(f => f.key === p.family)?.label || p.family,
}))
export const examples = Object.fromEntries(catalogue.products.map(p => [p.key, p.script.join('\n')]))
export function productTypeLabel(value) {
  return templateMeta.find(p => p.key === value)?.label || value || ''
}
