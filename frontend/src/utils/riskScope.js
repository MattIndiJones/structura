export function riskScopeLabel(value) {
  return { PRODUCTION: 'Production', UAT: 'Recette UAT' }[value] || 'Historique non qualifié'
}
