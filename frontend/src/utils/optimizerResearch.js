import { apiFetch } from './api.js'
import { responseError } from './productOptimizer.js'

export async function researchApi(path='',method='GET',body,signal) {
  const response=await apiFetch(`/api/product-optimizer/researches${path}`,{method,signal,
    ...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})})
  if(!response.ok) throw Error(await responseError(response))
  return response.json()
}
export const researchStatuses={RUNNING:'En cours',COMPLETED:'Terminée',PARTIAL:'Partielle',FAILED:'Erreur',INTERRUPTED:'Interrompue'}
export const percent=value=>value==null?'—':`${(value*100).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})} %`
export function downloadResearch(research) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(research,null,2)],{type:'application/json'}))
  const link=document.createElement('a');link.href=url;link.download=`structura-recherche-${research.id}.json`;link.click();URL.revokeObjectURL(url)
}

export const optimizerHelp={
  product_family:'Le script définit les règles de coupon, de rappel et de remboursement. Les champs et objectifs disponibles suivent ses paramètres qualifiés.',
  currency:'Devise commune aux sous-jacents et au règlement. Le calendrier ouvré et les hypothèses de taux doivent correspondre à cette devise.',
  underlying:'Un à trois titres du catalogue. Les trajectoires sont normalisées au fixing initial ; le panier multi-actif est évalué selon le worst-of du script.',
  asset_type:'Action ou indice d’après le référentiel du titre. La qualification manuelle est demandée uniquement si le type est inconnu.',
  put_strike:'Strike de la jambe put vendue, en % du fixing initial. La perte sous ce niveau suit la formule du script et son gearing.',
  gearing:'Multiplicateur de la perte de la jambe put, exprimé en fois (×). Dans ce script, la perte est plafonnée au nominal.',
  strike:'Strike de la participation à la hausse, en % du fixing initial. Il définit le niveau à partir duquel la hausse participe au remboursement.',
  decrement:'Baisse du seuil de rappel à chaque constatation après le rang de départ, en points de fixing initial ; le plancher reste applicable.',
  floor:'Niveau minimal du seuil de rappel dégressif, en % du fixing initial.',
  first_decrease_rank:'Rang de constatation à partir duquel le seuil de rappel commence à baisser.',
  intention:'Votre objectif métier en texte libre. Il reste associé au résumé normalisé des paramètres et aux résultats de cette recherche.',
  coupon_tolerance:'Écart maximal au coupon cible, en points de coupon annuel. L’objectif privilégie alors la protection parmi les solutions compatibles.',
  yield_curve:'Nœuds de taux zéro : maturité en années et taux annuel en %. La courbe remplace le taux plat pour le forward et l’actualisation.',
  dividend_curve:'Rendements de dividendes par bucket annuel, en %. Une courbe vide conserve le rendement plat ; le dernier bucket est prolongé.',
  funding_spread:'Spread de funding annuel, appliqué à l’actualisation seule. La valeur affichée dans les résultats est en % ; 100 bps = 1 %.',
  funding_curve:'Spread de funding par maturité en années, en %. La courbe active remplace le spread plat.',
  expected_coupon_paid:'Moyenne Q des coupons effectivement payés, non actualisés, en % du nominal, selon les règles de rappel et de mémoire du script.',
  expected_coupon_unpaid:'Moyenne Q des coupons manqués ou de la mémoire non payée à la terminaison, en % du nominal. Le sort des coupons dépend du script.',
  probability_capital_loss:'Probabilité Q de perte sur la jambe de capital, avant les coupons. Elle est distincte de la perte sur la somme de tous les flux.',
  conditional_capital_loss:'Perte moyenne de capital conditionnelle aux trajectoires qui subissent une perte de capital, en % du nominal, avant les coupons.',
  autocall_schedule:'Seuil de rappel à chaque constatation. La baisse et le plancher sont ceux du script figé avec la recherche.',
  objective:'Le paramètre ou le critère privilégié pour classer les structures. Les contraintes restent contrôlées séparément.',
  model:'GBM utilise une volatilité constante par titre. La volatilité réalisée chargée est une hypothèse de simulation, pas une cotation implicite de booking.',
  pricing_date:'Date d’arrêté du marché. Dans ce parcours à l’émission, elle est aussi le fixing initial et la date de valeur.',
  convention:'Ajustement des dates contractuelles selon les jours ouvrés de la devise choisie.',
  settlement_lag:'Nombre de jours ouvrés entre la constatation et le paiement. Les flux sont actualisés à leur date de paiement.',
  sigma:'Volatilité annualisée utilisée par GBM, en %. La référence historique et une surcharge manuelle restent distinctes.',
  q:'Rendement de dividende annuel utilisé pour le forward, en %. Le passé sert d’hypothèse future et peut être modifié.',
  correlation:'Corrélation des rendements des titres, de −1 à 1. Une matrice invalide est refusée sans correction automatique.',
  rate:'Taux sans risque en %. Il alimente le forward et l’actualisation ; une courbe active remplace le niveau plat.',
  funding:'Spread émetteur appliqué à l’actualisation seule. 100 bps correspondent à 1 % par an.',
  target_price:'Prix d’émission en % du nominal. Frais initiaux et marge sont soustraits pour déterminer le budget du payoff.',
  price_tolerance:'Écart maximal au budget du payoff, en points de nominal. Tout l’intervalle de contrôle du prix doit tenir dans cette plage.',
  costs:'Coût initial en points de nominal, déduit du prix d’émission. Le funding est déjà appliqué dans l’actualisation.',
  probability_loss:'Probabilité Q que les flux totaux non actualisés soient inférieurs au prix d’émission. Elle ne représente ni la probabilité réelle future ni un simple franchissement de barrière.',
  probability_autocall:'Probabilité Q d’un remboursement avant la dernière constatation. La borne basse de contrôle doit respecter le minimum demandé.',
  expected_maturity:'Durée moyenne sous Q jusqu’à la terminaison, en années ; elle peut être inférieure à la maturité contractuelle.',
  expected_capital_loss:'Perte moyenne Q de la jambe de capital, en % du nominal, avant coupons. La borne haute est comparée au plafond.',
  simulations:'Nombre de paires antithétiques indépendantes. Le calcul simule deux trajectoires par paire ; la validation utilise de nouveaux tirages à N et 2N.',
  budget:'Nombre de candidats, calculs simultanés et durée maximale. L’arrêt conserve les résultats disponibles avec une couverture partielle explicite.',
  fair_value:'Valeur actualisée du payoff, en % du nominal, sous le modèle et le marché figés dans cette recherche.',
  interval:'Intervalle de confiance utilisé pour le contrôle. L’exploration et la validation indépendante n’utilisent pas le même ajustement statistique.',
  status:'Vert : contraintes respectées et validation indépendante réussie. Rouge : hors conditions ou contrôle non concluant. Ambre : validation manquante.',
  coupon:'Coupon résolu en % du nominal. Le script précise la convention annuelle ou le coupon unique ; le montant effectivement payé dépend de ses règles de paiement.',
  participation:'Fraction de la hausse du sous-jacent versée à maturité, selon le payoff.',
  redemption_cap:'Plafond du remboursement total en % du nominal, distinct du seul gain.',
  protection_barrier:'Seuil de protection conditionnelle du capital, en % du fixing initial. Une barrière plus basse protège davantage ; le capital reste exposé sous cette barrière.',
  autocall_trigger:'Niveau du sous-jacent qui déclenche le rappel à une date de constatation autorisée.',
  coupon_barrier:'Niveau requis pour le paiement du coupon. La mémoire et le sort des coupons manqués dépendent du script.',
  maturity_months:'Maturité contractuelle en mois. Les fréquences et le calendrier doivent être compatibles avec le script.',
  observation_months:'Intervalle en mois entre constatations. Le coupon annuel est converti selon les règles du script.',
  parameter_mode:'Fixe conserve une valeur unique. À explorer parcourt minimum, maximum et pas ; la borne haute est incluse seulement si elle tombe sur le pas.',
  radar:'Comparaison descriptive de 2 à 4 structures. Chaque axe est normalisé avec une échelle explicite commune à la recherche. La surface ne constitue pas un score ni une recommandation.',
}
export const helpFor=key=>optimizerHelp[key] || 'Paramètre contractuel du script sélectionné ; sa valeur effective est transmise au calcul dans l’unité indiquée.'
