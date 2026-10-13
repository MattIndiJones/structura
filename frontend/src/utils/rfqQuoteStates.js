const publicationLabels = {
  ACTIVE: 'Active', WITHDRAWN: 'Retirée', REPLACED: 'Remplacée', RESERVED: 'Réservée au traitement',
  EXPIRED: 'Expirée', ROUND_CLOSED: 'Tour clôturé',
  PENDING_DELIVERY: 'Publiée · réception en attente', HISTORY: 'Historique · non sélectionnable',
}
const conditionLabels = { DOCUMENTATION: 'Documentation', CREDIT_APPROVAL: 'Accord crédit', OTHER: 'Autre condition' }
export const publicationStateLabel = value => publicationLabels[value] || 'État inconnu'
export const quoteConditionLabel = value => conditionLabels[value] || 'Condition à examiner'
