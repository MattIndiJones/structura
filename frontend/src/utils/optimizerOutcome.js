import { diagnosticFindings, diagnosticStatus } from './optimizerDiagnostics.js'

/** Separate provisional economic solutions from independent confirmation. */
export function researchOutcome(record) {
  const result=record.result,candidates=result?.candidates || [],validation=result?.validation || {}
  const confirmed=candidates.filter(c=>diagnosticStatus(c).tone==='good').length
  const admissible=validation.exploration_admissible ?? candidates.filter(c=>
    c.constraint_status==='PASS' || c.validation?.exploration?.constraint_status==='PASS').length
  const checked=candidates.filter(c=>['PASSED','REJECTED','FAILED'].includes(c.validation_status))
  const untested=candidates.filter(c=>c.constraint_status==='PASS' && c.validation_status!=='PASSED').length
  const precisionOnly=checked.length>0 && checked.every(c=>c.validation_status==='REJECTED' && !c.errors?.length &&
    c.rejection_details?.length && c.rejection_details.every(d=>d.category==='MC_UNCERTAINTY'))
  const simulations=record.request.search.simulations
  const nextSimulations=simulations<20000?Math.min(20000,Math.ceil(simulations*4/1000)*1000):null
  let title='',text='',tone='notice'
  if(record.status==='RUNNING') {
    if(record.progress?.phase==='validation') {
      title=`Validation indépendante en cours · ${checked.length} / ${record.progress.total || validation.selected || '—'} contrôlée(s)`
      text=`${admissible} structure(s) admissible(s) en exploration ; ${confirmed} confirmée(s) pour le moment. Le résultat définitif attend la fin des contrôles.`
    } else {
      title=`Exploration en cours · ${admissible} structure(s) admissible(s) provisoirement`
      text='Les prix apparaissent au fil du calcul. La validation indépendante des cinq meilleures structures admissibles intervient ensuite.'
    }
  } else if(confirmed) {
    title=`${confirmed} structure(s) confirmée(s)`;tone='good'
    text=`${admissible} admissible(s) en exploration ; ${checked.length} testée(s) indépendamment ; ${untested} autre(s) admissible(s) non confirmée(s).`
  } else if(precisionOnly) {
    title='Prix calculés, précision Monte-Carlo insuffisante pour confirmer la sélection';tone='pending'
    text=`${admissible} admissible(s) en exploration ; ${checked.length} testée(s) indépendamment, rejetée(s) pour incertitude statistique ; ${untested} autre(s) admissible(s) non validée(s).`
  } else {
    title='Aucune structure confirmée';tone=record.error?'bad':'notice'
    text=`${admissible} admissible(s) en exploration ; ${checked.length} testée(s) indépendamment ; ${untested} autre(s) admissible(s) non validée(s). Consultez les motifs de rejet ou de non-calcul.`
  }
  if(record.status!=='RUNNING' && (record.status==='PARTIAL' || record.status==='INTERRUPTED' || result?.complete===false))
    text+=' Couverture partielle : les calculs ou validations restants ne sont pas terminés.'
  const example=precisionOnly?checked.find(c=>c.rejection_details.some(d=>d.metric==='fair_value')):null
  const finding=example?diagnosticFindings(example,result).find(f=>f.reason.startsWith('Prix ')):null
  return {title,text,tone,admissible,confirmed,checked:checked.length,untested,precisionOnly,
    example:finding?`${example.candidate_id} : ${finding.reason}`:null,
    nextSimulations:record.status!=='RUNNING' && precisionOnly?nextSimulations:null}
}
