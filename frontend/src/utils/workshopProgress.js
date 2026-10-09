// Present only facts recorded by the controller or returned by Structura.
export const workshopLabels = {
  DRAFT:'Prête à démarrer', RUNNING:'En cours', PAUSING:'Pause en cours', PAUSED:'En pause',
  STOPPING:'Fermeture en cours', STOPPED:'Arrêtée', COMPLETED:'Terminée', ATTENTION:'Diagnostic nécessaire',
  SUCCESS:'Réussite', FAILED:'Échec', EXPECTED_REFUSAL:'Refus attendu', PENDING:'En attente',
  NO_TRADE:'Aucun trade — refus', MATCHED:'Rapprochement partiel', COMPLETE:'Quatre écritures rapprochées', MISMATCH:'Écart entre books',
}
const toolLabels = {
  register:'Créer ou reconnecter son compte', relationship:'Préparer les contrats', crm:'Créer le dossier client',
  propose:'Proposer une structure au client', request:'Exprimer un besoin client', rfq:'Lancer l’appel d’offres',
  quote:'Calculer et envoyer un prix', decline:'Refuser de coter', reprice:'Recalculer dans le Pricer',
  offer:'Proposer un prix au client', client_accept:'Répondre à l’offre client', accept_quote:'Confirmer le choix de banque',
  book:'Booker une opération', settle:'Enregistrer le règlement', review:'Suivre la vie des produits',
  risk:'Calculer le risque OTC hypothétique', mail:'Envoyer un message', browser:'Utiliser un écran',
  api:'Appeler Structura', report:'Signaler un problème', help:'Consulter les capacités de Structura', wait:'Attendre une réponse', model:'Interroger le modèle IA',
}
const legLabels = {BANK_SELL:'Vente banque → Hector', HECTOR_BUY:'Achat Hector ← banque', HECTOR_SELL:'Vente Hector → client', CLIENT_BUY:'Achat client ← Hector'}
export const actorName = (state, id) => state?.actors?.[id]?.name || id || 'Contrôleur'
export const actionTitle = action => action?.tool === 'book' ? legLabels[action.args?.leg] || toolLabels.book : toolLabels[action?.tool] || action?.tool || 'Décision IA'
export const money = value => new Intl.NumberFormat('fr-FR', {style:'currency',currency:'EUR',maximumFractionDigits:0}).format(value || 0)
const pct = value => new Intl.NumberFormat('fr-FR', {maximumFractionDigits:4}).format(value) + ' %'

export function actionEvidence(action) {
  const calls = action.http_calls || []
  const screen = ['UI','BROWSER'].includes(action.channel) || ['register','browser'].includes(action.tool)
  if (screen) return {kind:'screen', label: calls.length ? 'Écran + API' : 'Écran', detail: action.result?.screenshot ? 'Capture de l’écran disponible' : 'Action navigateur consignée, sans capture disponible'}
  if (calls.length) return {kind:'api', label:'API Structura', detail:`${calls.length} appel${calls.length > 1 ? 's' : ''} HTTP consigné${calls.length > 1 ? 's' : ''}`}
  if (action.tool === 'wait') return {kind:'wait', label:'Attente', detail:'Aucune opération métier exécutée'}
  if (action.tool === 'help') return {kind:'read', label:'Documentation API', detail:'Consultation des capacités de l’installation'}
  if (action.tool === 'report') return {kind:'report', label:'Signalement', detail:'Constat de l’agent à examiner'}
  if (['mail','request','client_accept'].includes(action.tool)) return {kind:'message', label:'Message interne', detail:'Échange entre agents ; aucune écriture de deal par ce message'}
  return {kind:'unknown', label:'Preuve à examiner', detail:'Aucun appel HTTP ni parcours écran consigné pour cette action'}
}

export function actionOutcome(action, state) {
  const r = action.result || {}, a = action.args || {}
  if (action.status === 'FAILED' || action.status === 'EXPECTED_REFUSAL') return r.error || workshopLabels[action.status]
  switch(action.tool) {
    case 'register': return r.username ? `Compte ${r.username} connecté dans son installation` : 'Résultat de connexion à examiner'
    case 'relationship': return `${actorName(state,a.party)} · relation ${r.status === 'ACTIVE' ? 'active' : r.status === 'PENDING' ? 'en attente de documentation' : r.status || 'enregistrée'}${r.master_agreement_id ? ' · ISDA enregistré' : ''}${r.csa_id ? ' · CSA enregistré' : ''}`
    case 'crm': return `Dossier client ${r.client_id ?? '—'} · mandat ${r.mandate_id ?? '—'}`
    case 'quote': return r.price != null ? `${r.case_id} · prix ${pct(r.price)} · marge ${a.margin_bps ?? '—'} pb` : 'Cotation à examiner'
    case 'offer': return `${r.case_id || ''} · offre client ${r.client_price != null ? pct(r.client_price) : '—'} · ${r.issuer || ''}`
    case 'book': return `Deal ${r.deal_reference || r.deal_id || '—'} · ${money(r.nominal)} · face à ${r.counterparty || '—'}`
    case 'request': return `${r.case_id || ''} · ${money(r.nominal)} · ${r.template || a.template || ''}`
    case 'rfq': return `RFQ ${r.rfq_id ?? '—'} envoyée à ${(r.recipients || []).map(id=>actorName(state,id)).join(', ')}`
    case 'accept_quote': return `Cotation retenue dans la RFQ ${r.rfq_id ?? '—'}`
    case 'client_accept': return r.accepted ? 'Le client accepte l’offre' : 'Le client refuse l’offre'
    case 'settle': return `${r.settled ?? 0} règlement(s) enregistré(s)`
    case 'review': return `${r.deals ?? 0} deal(s) revu(s) au ${r.date || action.date}`
    case 'risk': return `Calcul CCR ${r.run_id ?? '—'} · OTC hypothétique, distinct du risque des notes`
    case 'decline': return r.explanation || a.explanation || 'Refus de cotation'
    case 'mail': return `Message adressé à ${actorName(state,r.delivered || a.to)}${a.subject ? ' · '+a.subject : ''}`
    case 'propose': return 'Idée non cotée adressée au client et consignée dans le CRM'
    case 'wait': return r.explanation || a.explanation || 'Attend une réponse'
    case 'report': return r.description || a.description || 'Signalement conservé'
    case 'browser': return `Écran ${r.url || a.path || ''}`
    default: return workshopLabels[action.status] || action.status || 'Résultat disponible'
  }
}

export function usageProof(state, actorId) {
  const actions = (state?.actions || []).filter(a=>!actorId || a.actor === actorId)
  const result = {screens:0, apiActions:0, calls:0, messages:0, waits:0, failures:0}
  for (const action of actions) {
    const evidence = actionEvidence(action)
    if (evidence.kind === 'screen') result.screens++
    if (action.http_calls?.length) {result.apiActions++; result.calls += action.http_calls.length}
    if (evidence.kind === 'message') result.messages++
    if (evidence.kind === 'wait') result.waits++
    if (action.status === 'FAILED') result.failures++
  }
  return result
}

export function campaignRows(rows, current) {
  // The selected snapshot is newer than the separately loaded campaign listing.
  return rows.map(row=>{
    const next=row.id===current?.id ? {...row,status:current.status,turns:current.turns,business_date:current.business_date,...('controller_active' in current ? {controller_active:current.controller_active} : {})} : {...row}
    delete next.displayStatus
    if(next.controller_active===false&&['RUNNING','PAUSING','PAUSED','STOPPING'].includes(next.status))next.displayStatus='Exécution non confirmée'
    return next
  })
}

export function liveSummary(state) {
  const status = state?.status, activity = state?.activity
  if (status === 'COMPLETED') return {title:'Campagne terminée : aucun agent n’agit actuellement', detail:'Les échanges et preuves ci-dessous sont conservés. Les installations des acteurs sont fermées.', active:false}
  if (status === 'DRAFT') return {title:'Les IA n’ont pas encore démarré', detail:'Cliquez sur « Démarrer les IA » pour créer leurs installations et commencer le parcours.', active:false}
  if (state?.controller_active === false && ['RUNNING','PAUSING','PAUSED','STOPPING'].includes(status)) return {title:'Aucun contrôleur actif : les IA ne poursuivent plus la campagne', detail:'L’état enregistré est ancien. Relancez la campagne pour reprendre et vérifier ses installations privées.', active:false}
  if (status === 'STOPPED') return {title:'Campagne arrêtée : aucun agent en action', detail:'Les preuves sont conservées ; vous pouvez reprendre avec « Démarrer les IA ».', active:false}
  if (status === 'ATTENTION') return {title:'Le parcours s’est interrompu : diagnostic nécessaire', detail:'Consultez les derniers résultats et les bugs remontés avant de reprendre.', active:false}
  if (status === 'PAUSED') return {title:'Simulation en pause', detail:'Aucune nouvelle décision. Les installations restent disponibles pour inspection.', active:false}
  if (status === 'STOPPING') return {title:'Arrêt demandé : fermeture des installations', detail:'L’action en cours peut devoir se terminer avant la fermeture.', active:false}
  const prefix = status === 'PAUSING' ? 'Pause demandée · ' : ''
  if (activity?.phase === 'PREPARING') return {title:prefix+'Préparation des Structura des acteurs', detail:'Le contrôleur démarre les installations privées avant les inscriptions.', active:true}
  if (activity?.phase === 'THINKING') return {title:prefix+actorName(state,activity.actor)+' réfléchit à sa prochaine action', detail:'Le modèle IA est interrogé. Aucune nouvelle opération métier n’est encore exécutée pendant cette décision.', active:true}
  if (activity?.phase === 'EXECUTING') return {title:prefix+actorName(state,activity.actor)+' · '+actionTitle(activity), detail:activity.reason || 'Exécution de la décision choisie par l’IA.', active:true}
  return {title:prefix+'Campagne en cours · attente de la prochaine preuve', detail:'Le contrôleur n’a pas encore publié le détail de l’action courante. Les dernières actions terminées restent visibles.', active:true}
}

export function workflowSteps(state, caseId) {
  const actors = Object.entries(state?.actors || {}).map(([id,a])=>({id,...a})).filter(a=>a.role !== 'supervisor')
  const banks = actors.filter(a=>a.role === 'bank')
  const expectedRelations = banks.length * 2 + 2
  const relationCount = actors.reduce((n,a)=>n + Object.keys(a.relations || {}).length,0)
  const pending = actors.reduce((n,a)=>n + Object.values(a.relations || {}).filter(r=>r.status === 'PENDING').length,0)
  const cases = Object.values(state?.cases || {}).sort((a,b)=>(a.month-b.month) || a.id.localeCompare(b.id))
  const c = cases.find(c=>c.id === caseId) || cases.find(c=>c.month === state?.month) || cases.at(-1)
  const quotes = (state?.quotes || []).filter(q=>q.case_id === c?.id)
  const responded = banks.filter(b=>quotes.some(q=>q.bank===b.id) || c?.declines?.includes(b.id)).length
  const check = state?.book_checks?.find(b=>b.case_id === c?.id)
  const declined = ['CLIENT_DECLINED','NO_QUOTE'].includes(c?.outcome)
  const bookActors = actors.filter(a=>a.deals?.length)
  const reviewed = bookActors.length > 0 && bookActors.every(a=>a.last_review?.date === state.business_date && a.last_review.deals === a.deals.length && a.deals.every(d=>d.settlement_status === 'SETTLED'))
  const steps = [
    {title:'Comptes', done:actors.length>0 && actors.every(a=>a.registered), detail:`${actors.filter(a=>a.registered).length} / ${actors.length} comptes utilisés`},
    {title:'Contrats', done:relationCount>=expectedRelations, warning:pending>0, detail:`${relationCount} / ${expectedRelations} relations enregistrées${pending ? ' · '+pending+' incomplète(s)' : ''}`},
    {title:'Besoin client', done:!!c, detail:c ? `${c.id} · ${money(c.nominal)}` : 'Aucun besoin reçu'},
    {title:'Appel d’offres', done:!!c?.rfq_sent && responded === banks.length, detail:c?.rfq_sent ? `${responded} / ${banks.length} réponses · ${quotes.length} prix` : 'Pas encore envoyé'},
    {title:'Accords', done:!!state?.accepted?.[c?.id], skipped:declined, detail:c?.outcome==='NO_QUOTE' ? 'Aucune banque ne cote' : c?.outcome==='CLIENT_DECLINED' ? 'Le client a refusé' : state?.accepted?.[c?.id] ? 'Client et banque confirmés' : state?.client_acceptances?.includes(c?.id) ? 'Accord client · banque à confirmer' : state?.client_offers?.[c?.id] ? 'Offre client envoyée' : 'Offre client attendue'},
    {title:'Booking', done:check?.status==='COMPLETE', skipped:declined, warning:check?.status==='MISMATCH', detail:declined ? 'Sans trade' : `${check?.legs || 0} / 4 écritures${check?.status==='MISMATCH' ? ' · écart' : ''}`},
    {title:'Suivi de vie', done:reviewed, skipped:declined && !bookActors.length, detail:reviewed ? `Books revus au ${state.business_date}` : bookActors.length ? 'Règlements / revue en attente' : 'Aucun book à revoir'},
  ]
  const firstPending = steps.findIndex(s=>!s.done && !s.skipped)
  return {caseId:c?.id, steps:steps.map((s,i)=>({...s, state:s.warning?'warning':s.skipped?'skipped':s.done?'done':i===firstPending?'current':'pending'}))}
}
