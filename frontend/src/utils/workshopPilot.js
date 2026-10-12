import { workflowSteps } from './workshopProgress'

export function durationLabel(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0))
  const hours = Math.floor(value / 3600), minutes = Math.floor(value % 3600 / 60)
  return hours ? `${hours} h ${minutes} min` : minutes ? `${minutes} min ${value % 60} s` : `${value} s`
}

export function pilotSummary(state) {
  const checks = state.book_checks || []
  const months = Math.min(state.month || 0, state.config.months)
  const completed = checks.filter(c => c.status === 'COMPLETE').length
  const refusals = checks.filter(c => c.status === 'NO_TRADE').length
  const uncertain = checks.filter(c => ['MISMATCH', 'UNVERIFIED'].includes(c.status)).length
  const remaining = Math.max(0, state.config.max_turns - state.turns)
  const active = state.controller_active === true && ['RUNNING', 'PAUSING', 'PAUSED', 'STOPPING'].includes(state.status)
  let advice = '', action = ''
  if (state.status === 'COMPLETED') advice = 'La période est terminée. Consultez les opérations et les points ouverts, ou recommencez une partie vierge.'
  else if (state.status !== 'DRAFT' && remaining === 0) {
    advice = 'Budget de décisions épuisé. Préparez une nouvelle campagne avec un budget supérieur ; cet historique reste conservé.'
    action = 'configure'
  } else if (state.status === 'PAUSED' && active) {
    advice = state.pause_reason === 'RECONCILIATION' ? 'Le rapprochement des books a suspendu la partie. Examinez les écarts et les preuves avant de reprendre.' : state.pause_reason === 'ERROR' ? 'La partie est suspendue après plusieurs erreurs. Examinez la dernière preuve avant de reprendre.' : state.pause_reason === 'IDLE' ? 'Les acteurs attendent sans clôturer le dossier. Examinez les échanges et les écritures encore attendues.' : 'La partie est en pause. Vous pouvez inspecter les preuves puis reprendre.'
    action = 'resume'
  } else if (state.status !== 'DRAFT' && !active && state.status !== 'STOPPING') {
    advice = 'Les IA sont arrêtées. Consultez le dernier résultat puis reprenez les données existantes, ou recommencez avec des comptes vierges.'
    action = 'start'
  }
  const workflow = workflowSteps(state)
  return {months, completed, refusals, uncertain, remaining, active, advice, action,
    percent: state.config.months ? Math.round(100 * months / state.config.months) : 0,
    next: state.status === 'COMPLETED' ? 'Période terminée' : workflow.steps.find(s => !s.done && !s.skipped)?.title || 'Revue finale',
    pending: checks.filter(c => ['PENDING', 'MATCHED', 'UNVERIFIED'].includes(c.status)).length}
}

export function timelinePage(items, {actor = '', caseId = '', query = '', status = '', page = 1, size = 25, messages = false} = {}) {
  const needle = query.trim().toLocaleLowerCase('fr-FR')
  const filtered = items.map((item, index) => ({...item, journalIndex: index})).filter(item => {
    const reference = item.case_id || item.args?.case_id || item.result?.case_id || item.attachment?.case_id || ''
    return (!actor || (messages ? item.from === actor || item.to === actor : item.actor === actor)) &&
      (!caseId || reference === caseId) && (!status || item.status === status) &&
      (!needle || JSON.stringify(item).toLocaleLowerCase('fr-FR').includes(needle))
  }).reverse()
  const pages = Math.max(1, Math.ceil(filtered.length / size)), current = Math.max(1, Math.min(page, pages))
  return {items: filtered.slice((current - 1) * size, current * size), total: filtered.length, pages, page: current}
}

export function matchedBankVolumes(state) {
  const complete = new Set((state.book_checks || []).filter(c => c.status === 'COMPLETE').map(c => c.case_id))
  const result = Object.fromEntries(Object.entries(state.actors || {}).filter(([, a]) => a.role === 'bank').map(([id, a]) =>
    [id, (a.deals || []).filter(d => d.leg === 'BANK_SELL' && complete.has(d.case_id)).reduce((sum, d) => sum + d.nominal, 0)]))
  return {result, total: Object.values(result).reduce((sum, amount) => sum + amount, 0)}
}
