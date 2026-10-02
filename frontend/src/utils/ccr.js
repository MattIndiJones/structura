import { apiFetch } from './api.js'
import { readMtmResponse } from '../composables/useBookingMtm.js'

export async function ccrCalculate(body, onProgress) {
  const response = await apiFetch('/api/ccr/calculate?stream=true', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  return readMtmResponse(response, onProgress, 'Flux CCR interrompu : vérifier le monitor avant de relancer le calcul.')
}

export const valuationSources = {
  CCR_BASE_REUSED: 'MtM de base réutilisé sans recalcul',
  CCR_COMMON_MARKET_REVALUED: 'MtM recalculé sur marché commun', SAVED_MTM_REUSED: 'MtM compatible réutilisé', SAVED_CONTEXT_REVALUED: 'MtM recalculé sur contexte figé',
  SAVED_RESIDUAL_CONTEXT: 'Contexte figé réutilisé', CCR_RESIDUAL_MTM: 'MtM calculé dans CCR',
}

export async function ccrApi(path, body, method = 'POST') {
  const response = await apiFetch(`/api/ccr${path}`, body === undefined ? {} : {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data))
  return data
}

export const metricLabels = {
  gross_notional: 'Nominal brut', gross_positive_mtm: 'MtM positif brut', net_mtm: 'MtM net',
  collateral: 'Collatéral reconnu net', collateral_held: 'Collatéral reçu', collateral_posted: 'Collatéral posté',
  current_exposure: 'Exposition courante / coût de remplacement', ee: 'Exposition attendue moyenne — EPE',
  pfe95: 'Exposition future potentielle — PFE 95 %', pfe99: 'PFE 99 %', maximum_pfe: 'PFE 95 % maximale',
  cva: 'Ajustement de valeur de crédit — CVA', ead: 'Exposition au défaut — EAD', stressed_exposure: 'Exposition stressée',
}
export const statusLabels = {
  OK: 'OK', WARNING: 'Alerte', LIMIT_REACHED: 'Limite atteinte', BREACH: 'Dépassement',
  NO_LIMIT: 'NO LIMIT DEFINED — aucune limite définie', MISSING_DATA: 'Données manquantes', NOT_APPLICABLE: 'Non applicable',
}
export function number(v, decimals = 0) {
  if (v === null || v === undefined || v === '' || !Number.isFinite(Number(v))) return '—'
  return new Intl.NumberFormat('fr-FR', { useGrouping: true, minimumFractionDigits: decimals, maximumFractionDigits: decimals })
    .formatToParts(Number(v)).map(p => p.type === 'group' ? '\u00a0' : p.value).join('')
}
export const money = v => number(v, 2)
export const percent = v => v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? '—' : `${number(Number(v) * 100, 1)} %`

export const fieldLabels = {
  legal_name: 'Raison sociale', short_name: 'Nom court', lei: 'LEI', counterparty_type: 'Type de contrepartie',
  parent_group: 'Groupe parent', currency: 'Devise', internal_rating: 'Notation interne', external_rating: 'Notation externe',
  recovery: 'Taux de recouvrement (fraction : 0,40 = 40 %)', recovery_source: 'Provenance du recouvrement',
  curve_source: 'Source de la courbe de crédit', pd_measure: 'Mesure de probabilité de défaut',
  pd_curve: 'PD cumulées : [[année, probabilité]]', spread_curve: 'Spreads : [[année, spread en fraction]]',
  has_isda: 'Accord ISDA connu', has_csa: 'Annexe de collatéral CSA connue',
  agreement_id: 'Référence de l’accord ISDA', agreement_version: 'Version contractuelle', effective_date: 'Date d’effet',
  governing_law: 'Droit applicable', status: 'Statut', legal_opinion_available: 'Avis juridique disponible',
  close_out_netting_enforceable: 'Compensation de clôture opposable', cross_product_netting_allowed: 'Netting inter-produits autorisé',
  notes: 'Notes', csa_id: 'Référence CSA', master_agreement_id: 'Accord ISDA', bilateral: 'Bilatéral',
  collateralised: 'Collatéralisé', vm_required: 'Marge de variation — VM requise', vm_frequency_days: 'Fréquence VM (jours ouvrés)',
  threshold_counterparty: 'Seuil contrepartie', threshold_our_side: 'Seuil de notre entité', mta: 'Transfert minimum — MTA',
  independent_amount: 'Montant indépendant', im_required: 'Marge initiale — IM requise', im_model: 'Modèle IM (V1 : FIXED)',
  im_amount: 'Montant IM contractuel', segregated: 'IM ségréguée', im_recognised: 'IM reçue juridiquement reconnue',
  base_currency: 'Devise de base', eligible_collateral: 'Actifs éligibles : ["CASH"]', collateral_haircut: 'Décote (fraction)',
  settlement_lag_days: 'Délai de règlement (jours ouvrés)', mpor_days: 'Période de risque de marge — MPOR (jours ouvrés)',
  active: 'Actif', netting_set_id: 'Netting set', product_scope: 'Types de produits autorisés : ["Autocall"]',
  our_legal_entity: 'Notre entité juridique', counterparty_legal_entity: 'Entité juridique contrepartie',
  enforceable_netting: 'Netting opposable', metric: 'Métrique de limite', amount: 'Montant',
  warning_threshold: 'Seuil alerte (0,80 = 80 %)', hard_threshold: 'Seuil dur (1 = 100 %)', action: 'Politique de limite',
  expiry_date: 'Expiration', as_of_date: 'Date d’arrêté', collateral_type: 'Type de collatéral', held: 'VM reçue',
  posted: 'VM postée', im_held: 'IM reçue (hors VM)', recognised: 'Position juridiquement reconnue', source: 'Source',
  limit_id: 'Limite concernée', requested_by: 'Demandeur (ID)', approved_by: 'Approbateur (ID)', reason: 'Motif',
  previous_limit: 'Limite précédente', temporary_limit: 'Limite temporaire demandée',
}
