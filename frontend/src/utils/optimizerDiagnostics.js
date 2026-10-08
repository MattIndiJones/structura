const finite=value=>typeof value==='number' && Number.isFinite(value)
const number=value=>Number(value).toLocaleString('fr-FR',{minimumFractionDigits:2,maximumFractionDigits:2})
const percent=value=>`${number(value*100)} %`
const amount=(value,unit)=>unit==='years'?`${number(value)} ans`:percent(value)

export function pricingTarget(result) {
  const request=result?.request
  return result?.economics?.pricing_target ?? (request?.constraints?.target_price == null ? null :
    request.constraints.target_price-(request.economics?.upfront_fees || 0)-(request.economics?.structuring_margin || 0))
}

/** Economic ordering is separate from admission: rejected prices stay visible. */
export function diagnosticCandidates(result,family) {
  const candidates=(result?.candidates || []).filter(c=>c.pricing_status==='PRICED' && finite(c.fair_value))
  const objective=result?.request?.objective
  const solved=family?.solved_field?.key || 'coupon'
  const axes=objective==='maximize_coupon' ? [[solved,-1],['probability_loss',1],['protection_barrier',1]] :
    ['maximize_participation','maximize_cap'].includes(objective) ? [[solved,-1],['probability_loss',1],
      [family?.frontier?.x?.key,family?.frontier?.x?.preference==='max'?-1:1]] :
    result?.request?.product_family==='autocall_gear_put' ? [['expected_capital_loss',1],['put_strike',1],['gearing',1],['coupon',-1]] :
      [['protection_barrier',1],['probability_loss',1],['coupon',-1]]
  if(result?.request?.product_family==='autocall_gear_put' && objective==='maximize_coupon')
    axes.splice(1,axes.length-1,['expected_capital_loss',1],['put_strike',1],['gearing',1])
  return [...candidates].sort((a,b)=>{
    for(const [key,direction] of axes) {
      if(finite(a[key])!==finite(b[key])) return finite(a[key])?-1:1
      if(finite(a[key]) && a[key]!==b[key]) return direction*(a[key]-b[key])
    }
    return a.candidate_id.localeCompare(b.candidate_id)
  })
}

export function diagnosticStatus(candidate) {
  if(candidate.pricing_status==='FAILED' || candidate.validation_status==='FAILED' || candidate.errors?.length)
    return {tone:'bad',label:'Erreur de calcul / validation'}
  if(candidate.constraint_status==='PASS' && candidate.validation_status==='PASSED')
    return {tone:'good',label:'Confirmée — conditions respectées'}
  if(candidate.pricing_status!=='PRICED') return {tone:'bad',label:'Non résolue / non pricée'}
  if(candidate.constraint_status==='REJECTED') {
    const details=candidate.rejection_details || []
    const onlyUncertainty=details.length && details.every(d=>d.category==='MC_UNCERTAINTY')
    return {tone:'bad',label:onlyUncertainty?'Non confirmée — incertitude Monte-Carlo':'Hors conditions'}
  }
  return {tone:'pending',label:'Exploration admissible — validation manquante'}
}

/** Describe actual measured failures using the frozen request, not edited inputs. */
export function diagnosticFindings(candidate,result,{running=false}={}) {
  const findings=[]
  for(const error of candidate.errors || []) findings.push({reason:error,action:'Vérifier les journaux du calcul ; une modification des contraintes ne corrige pas une erreur technique.'})
  for(const detail of candidate.rejection_details || []) {
    let reason=detail.label,action='Revoir les paramètres concernés puis recalculer.'
    if(detail.metric==='fair_value' && detail.interval?.length===2 && finite(detail.target) && finite(detail.tolerance)) {
      const intervalLabel=candidate.validation?.runs?.length?'intervalle de contrôle simultané':'IC95'
      reason=`Prix ${percent(detail.estimate)} ; ${intervalLabel} ${detail.interval.map(percent).join(' – ')}. Plage demandée ${percent(detail.target-detail.tolerance)} – ${percent(detail.target+detail.tolerance)}.`
      const required=Math.ceil(Math.max(...detail.interval.map(v=>Math.abs(v-detail.target)))*10000-1e-9)/100
      action=detail.category==='MC_UNCERTAINTY' ?
        `Prix central dans la tolérance, intervalle trop large : augmenter les simulations et recalculer. Tolérance couvrant cet intervalle : ${number(required)} points de nominal, à examiner si acceptable.` :
        'Prix central hors tolérance : revoir les bornes du paramètre résolu ou le prix cible, puis recalculer.'
    } else if(finite(detail.bound) && finite(detail.limit)) {
      const minimum=detail.metric==='probability_autocall'
      reason=`${detail.label} : estimation ${amount(detail.estimate,detail.unit)}, borne de contrôle ${amount(detail.bound,detail.unit)}, ${minimum?'minimum':'plafond'} ${amount(detail.limit,detail.unit)} ; écart ${amount(detail.gap,detail.unit)}.`
      action=detail.category==='MC_UNCERTAINTY' ? 'Estimation centrale conforme, borne statistique non conforme : augmenter les simulations et recalculer.' :
        `Revoir la structure ou la limite : ${minimum?'minimum au plus égal à':'plafond au moins égal à'} ${amount(detail.bound,detail.unit)} pour respecter cette borne calculée.`
    } else if(detail.metric==='coupon' && finite(detail.target)) {
      reason=`Coupon ${percent(detail.estimate)} ; cible ${percent(detail.target)} ± ${percent(detail.tolerance)}.`
      action='Revoir le coupon cible, sa tolérance ou les axes de recherche, puis recalculer.'
    } else if(detail.endpoint_prices?.some(finite)) {
      reason=`${detail.label}. Prix aux bornes : ${detail.endpoint_prices.map(v=>finite(v)?percent(v):'indisponible').join(' / ')} ; cible ${percent(detail.target)}.`
      action=detail.category==='NUMERICAL_SOLVER' ? 'La cible est encadrée : vérifier la convergence de la résolution avant de modifier le contrat.' :
        `Revoir les bornes de ${result?.payoff?.solved_field?.label || 'la variable résolue'} ou le prix cible. Aucun prix de structure complète n’est confirmé à ce stade.`
    } else if(detail.category==='MC_UNCERTAINTY') {
      action='Contrôle N/2N non concluant : augmenter les simulations et recalculer ; si l’écart persiste, examiner les diagnostics numériques.'
    } else if(detail.category==='CONTRACT_OR_BOUNDS') {
      action='Revoir les bornes et le calendrier du payoff indiqués dans le motif de rejet.'
    }
    findings.push({reason,action})
  }
  if(!findings.length && candidate.rejection_reasons?.length)
    for(const reason of candidate.rejection_reasons) findings.push({reason,action:'Vérifier la condition indiquée puis recalculer.'})
  if(!findings.length) {
    const status=diagnosticStatus(candidate)
    findings.push({reason:status.label,action:status.tone==='good'?'Aucun blocage sur les contrôles effectués.':
      running?'Calcul en cours : attendre la sélection et la validation indépendante avant de conclure.':
      candidate.validation_status==='PENDING'?'Validation non terminée : reprendre une recherche ciblée pour la terminer.':'Validation indépendante nécessaire ; cibler cette structure dans une nouvelle recherche.'})
  }
  return findings
}
