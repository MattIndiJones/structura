export const reconciliationLabels = {
  DECISION_PENDING: 'Décision bancaire encore attendue', PEER_UNKNOWN: 'État du livre distant inconnu',
  BOTH_BOOKINGS_MISSING: 'Accord confirmé · aucun des deux bookings déclaré',
  LOCAL_BOOKING_MISSING: 'Booking local manquant · livre distant booké',
  PEER_BOOKING_MISSING: 'Booking local inscrit · livre distant incomplet',
  MATCHED_PENDING_DELIVERY: 'Économies concordantes · remise de notre état à confirmer',
  MATCHED: 'Exécution et bookings rapprochés', MISMATCH: 'Écart à examiner · aucune correction automatique',
  REJECTED: 'Refus concordant · aucun booking attendu',
}
