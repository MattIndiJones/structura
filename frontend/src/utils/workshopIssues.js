import { actorName, actionTitle } from './workshopProgress'

export const issueCategories = {
  structura:'Appels Structura à diagnostiquer', agent:'Erreurs IA / usage', pilot:'Problèmes du pilote de test',
  reported:'Bugs signalés par une IA', improvement:'Améliorations / fonctions manquantes', other:'Autres points à examiner',
}

function linkedAction(state, incident) {
  const actions=state.actions || []
  const exact=actions[incident.action_index]
  if(exact?.actor===incident.actor && exact.status==='FAILED' && exact.result?.error===incident.description)return incident.action_index
  return actions.findIndex(a=>a.actor===incident.actor && ((a.tool==='report'&&a.result?.id===incident.id) || (a.status==='FAILED'&&a.result?.error===incident.description)))
}

function categoryFor(incident, action) {
  if(incident.kind==='HARNESS')return 'pilot'
  if(incident.source==='AGENT')return incident.kind==='BUG' ? 'reported' : incident.kind==='USAGE' ? 'agent' : ['IMPROVEMENT','MISSING'].includes(incident.kind) ? 'improvement' : 'other'
  if(action?.http_calls?.some(c=>c.status>=400))return 'structura'
  if(action?.status==='FAILED')return 'agent'
  return 'other'
}

function explanationFor(incident, action, category) {
  const error=incident.description || ''
  if(action?.tool==='mail'&&/Intervenant inconnu/i.test(error))return {summary:'L’IA a choisi un destinataire qui n’existe pas dans la messagerie de la campagne.', next:`Vérifier le destinataire « ${action.args?.to || '—'} » et les correspondants proposés à l’IA. Une adresse mail externe n’est pas un identifiant d’acteur de cette simulation.`}
  if(/PRICING_RECEIPT/i.test(error))return {summary:'Structura a refusé le booking car la preuve serveur du pricing est invalide.',next:'Vérifier le reçu, son installation d’origine et les reprises de session ; recalculer le prix dans la même installation avant de retenter. Le refus observé ne démontre pas à lui seul un bug de Structura.'}
  if(action?.http_calls?.some(c=>c.status===404))return {summary:'L’agent a appelé une route que son installation n’a pas trouvée.',next:'Comparer le chemin demandé aux capacités OpenAPI de cette installation et à la décision de l’IA. Une route inventée est une erreur d’usage ; une route attendue absente demande un diagnostic de l’application.'}
  if(category==='pilot')return {summary:'Le contrôleur ou le navigateur de recette a remonté un problème de pilotage.',next:'Examiner les actions précédentes et les journaux des installations. Une pause de diagnostic conserve les preuves ; elle n’est pas un bug métier confirmé.'}
  if(category==='reported')return {summary:'Une IA considère ce comportement comme un bug ; aucune confirmation humaine n’est enregistrée.',next:'Reproduire avec les données et la preuve de l’action, comparer le résultat attendu au résultat obtenu, puis confirmer ou reclasser le signalement.'}
  if(category==='improvement')return {summary:'Suggestion ou fonction/documentation manquante signalée par l’agent.',next:'Vérifier si le manque est volontaire dans le scénario ou s’il nécessite une évolution de Structura.'}
  if(category==='structura')return {summary:'Un appel natif à Structura a reçu une réponse d’erreur.',next:'Examiner la réponse HTTP, les arguments, les droits et les contrats. Distinguer un contrôle métier attendu d’un comportement incorrect avant de décider du correctif.'}
  return {summary:category==='agent' ? 'L’action ou l’explication de l’IA nécessite une vérification.' : 'Point conservé sans diagnostic suffisant.',next:'Examiner l’action liée et les échanges précédents. Définir le résultat attendu avant de conclure à un bug.'}
}

export function campaignIssues(state) {
  const actions=state?.actions || [], incidents=state?.incidents || []
  const rows=incidents.map((incident,index)=>{
    const actionIndex=linkedAction(state,incident), action=actions[actionIndex]
    const category=categoryFor(incident,action)
    return {...incident,number:index+1,actionIndex,action,category,...explanationFor(incident,action,category),qualification:'À examiner — non confirmé'}
  })
  // Older journals may contain failures without a separate incident. Keep them visible.
  actions.forEach((action,index)=>{
    if(action.status!=='FAILED'||rows.some(row=>row.actionIndex===index))return
    const incident={id:`action-${index}`,actor:action.actor,date:action.date,source:'ACTION',kind:'TO_DIAGNOSE',description:action.result?.error || 'Échec sans message détaillé'}
    const category=categoryFor(incident,action)
    rows.push({...incident,number:rows.length+1,actionIndex:index,action,category,...explanationFor(incident,action,category),qualification:'À examiner — non confirmé'})
  })
  return rows
}

export function issueReport(state, rows=campaignIssues(state)) {
  return [`Signalements de recette — ${state.config.name}`,`Campagne : ${state.id}`,`Date du jeu : ${state.business_date}`,
    'Ces fiches sont des observations à diagnostiquer, pas une liste de bugs confirmés.',
    ...rows.flatMap(row=>['',`POINT ${row.number} — ${issueCategories[row.category]}`,`Acteur : ${actorName(state,row.actor)} · date du jeu : ${row.date}`,
      `Source : ${row.source} · ${row.qualification}`,`Observation : ${row.summary}`,`Message original : ${row.description}`,
      `À vérifier : ${row.next}`,row.action ? `Action ${row.actionIndex+1} : ${actionTitle(row.action)}\nDécision : ${row.action.reason}\nArguments : ${JSON.stringify(row.action.args)}\nRéponses HTTP : ${JSON.stringify(row.action.http_calls || [])}\nRésultat : ${JSON.stringify(row.action.result)}` : 'Aucune action liée avec certitude dans le journal.'])].join('\n')
}
