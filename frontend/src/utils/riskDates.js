export function localTodayIso(now = new Date()) {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function dealRiskState(deal, valuationDate) {
  if (!valuationDate) return { active: false, reason: 'Date d’analyse manquante' }
  if (deal.trade_date && valuationDate < deal.trade_date) {
    return { active: false, reason: `Pas encore booké · ${deal.trade_date}` }
  }
  if (deal.risk_terminal_date && valuationDate >= deal.risk_terminal_date) {
    return { active: false, reason: `Terminé · ${deal.risk_terminal_date}` }
  }
  if (!deal.risk_terminal_date && !['actif', 'en_reglement'].includes(deal.status)) {
    return { active: false, reason: `Statut ${deal.status}` }
  }
  return { active: true, reason: 'Actif à cette date' }
}
